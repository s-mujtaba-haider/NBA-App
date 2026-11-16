"""Login, profile, API keys, user administration, and desktop license activation."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import User, get_db
from ..security import (
    current_user, generate_api_key, hash_key, issue_license_token, key_status, make_legacy_code, public_key_pem,
    require_admin, sign_license, user_by_key, validate_legacy_code, verify_license,
)

logger = logging.getLogger("auth")
router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    identifier: str
    api_key: str


def _profile(u: User) -> dict:
    ok, msg = key_status(u)
    return {"id": u.id, "identifier": u.identifier, "plan": u.plan, "role": u.role, "is_active": u.is_active,
            "license_valid": ok, "license_message": msg,
            "key_start_date": u.key_start_date.isoformat() if u.key_start_date else None,
            "key_end_date": u.key_end_date.isoformat() if u.key_end_date else None,
            "api_key_prefix": u.api_key_prefix, "devices": len(u.devices or []),
            "max_devices": u.max_devices}


@router.post("/login", summary="Login")
def login(body: LoginRequest, session: Session = Depends(get_db)):
    user = user_by_key(session, body.api_key)
    if user is None or user.identifier.lower() != body.identifier.strip().lower():
        raise HTTPException(status_code=401, detail="Invalid credentials")
    ok, msg = key_status(user)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)
    logger.info("Login: %s", user.identifier)
    return {"status": "ok", "identifier": user.identifier, "api_key": body.api_key, "plan": user.plan, "role": user.role}


@router.get("/profile", summary="Profile")
def profile(user: User = Depends(current_user)):
    return _profile(user)


@router.post("/users/{user_id}/rotate-key", summary="Rotate Api Key (self or admin)")
def rotate_key(user_id: int, session: Session = Depends(get_db),
               x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
               x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    caller = user_by_key(session, x_api_key) if x_api_key else None
    is_admin = False
    try:
        require_admin(x_admin_token, x_api_key, session)
        is_admin = True
    except HTTPException:
        pass
    if not is_admin and (caller is None or caller.id != user_id):
        raise HTTPException(status_code=403, detail="You can only rotate your own key")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_key = generate_api_key()
    user.api_key_hash, user.api_key_prefix = hash_key(new_key), new_key[:4]
    user.devices = []
    session.commit()
    return {"status": "ok", "user_id": user.id, "api_key": new_key,
            "message": "Store this key now; it cannot be shown again. Desktop installs must re-activate."}


# ---- Admin user management -------------------------------------------------------------------------
class UserCreate(BaseModel):
    identifier: str
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD, default today")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    days: Optional[int] = Field(None, description="Alternative to end_date")
    plan: str = "pro"
    role: str = Field("user", pattern="^(user|admin)$")
    max_devices: int = Field(2, ge=1, le=50)
    notes: Optional[str] = None
    api_key: Optional[str] = Field(None, description="Use a specific key (default: generated)")


class UserUpdate(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: Optional[bool] = None
    plan: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(user|admin)$")
    max_devices: Optional[int] = Field(None, ge=1, le=50)
    notes: Optional[str] = None
    reset_devices: bool = False


def _dt(s: str) -> datetime:
    return datetime.combine(date.fromisoformat(s), datetime.min.time(), tzinfo=timezone.utc)


@router.post("/admin/users", summary="Create a user / license (admin)")
def create_user(body: UserCreate, session: Session = Depends(get_db), _: str = Depends(require_admin)):
    if session.execute(select(User).where(User.identifier == body.identifier.strip())).scalar_one_or_none():
        raise HTTPException(409, "A user with this identifier already exists")
    start = _dt(body.start_date) if body.start_date else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if body.end_date:
        end = _dt(body.end_date) + timedelta(hours=23, minutes=59, seconds=59)
    else:
        end = start + timedelta(days=body.days or 30, hours=23, minutes=59, seconds=59)
    if end <= start:
        raise HTTPException(422, "end_date must be after start_date")
    key = body.api_key or generate_api_key()
    u = User(identifier=body.identifier.strip(), api_key_hash=hash_key(key), api_key_prefix=key[:4],
             key_start_date=start, key_end_date=end, plan=body.plan, role=body.role, max_devices=body.max_devices,
             notes=body.notes, devices=[])
    session.add(u)
    session.commit()
    logger.info("Created user %s (%s -> %s)", u.identifier, start.date(), end.date())
    return {**_profile(u), "api_key": key, "message": "Give the user their email and this key. It is shown only once."}


@router.get("/admin/users", summary="List users (admin)")
def list_users(session: Session = Depends(get_db), _: str = Depends(require_admin)):
    return {"users": [_profile(u) for u in session.execute(select(User).order_by(User.id)).scalars()]}


@router.patch("/admin/users/{user_id}", summary="Update a user (admin)")
def update_user(user_id: int, body: UserUpdate, session: Session = Depends(get_db), _: str = Depends(require_admin)):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if body.start_date:
        u.key_start_date = _dt(body.start_date)
    if body.end_date:
        u.key_end_date = _dt(body.end_date) + timedelta(hours=23, minutes=59, seconds=59)
    for k in ("is_active", "plan", "role", "max_devices", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(u, k, v)
    if body.reset_devices:
        u.devices = []
    session.commit()
    return _profile(u)


@router.delete("/admin/users/{user_id}", summary="Delete a user (admin)")
def delete_user(user_id: int, session: Session = Depends(get_db), _: str = Depends(require_admin)):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    session.delete(u)
    session.commit()
    return {"status": "deleted", "user_id": user_id}


class LegacyCodeRequest(BaseModel):
    start_date: str
    end_date: str


@router.post("/admin/legacy-code", summary="Generate a legacy-format activation code (admin)")
def legacy_code(body: LegacyCodeRequest, _: str = Depends(require_admin)):
    try:
        return {"activation_code": make_legacy_code(body.start_date, body.end_date)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- Desktop license -------------------------------------------------------------------------------
class ActivateRequest(BaseModel):
    identifier: str = Field(description="Email / identifier")
    license_key: str
    device_id: str = Field(min_length=8, max_length=128)
    device_name: Optional[str] = None


class ValidateRequest(BaseModel):
    token: str
    device_id: str


@router.get("/license/public-key", tags=["license"], summary="Public key that verifies license tokens")
def license_public_key():
    return {"algorithm": "Ed25519", "public_key_pem": public_key_pem()}


@router.post("/license/activate", tags=["license"], summary="Activate a desktop install")
def activate(body: ActivateRequest, session: Session = Depends(get_db)):
    user = user_by_key(session, body.license_key)
    if user is not None:
        if user.identifier.lower() != body.identifier.strip().lower():
            raise HTTPException(401, "Email and license key do not match")
        ok, msg = key_status(user)
        if not ok:
            raise HTTPException(403, msg)
        devices: List[dict] = list(user.devices or [])
        known = next((d for d in devices if d.get("id") == body.device_id), None)
        if known is None:
            if len(devices) >= user.max_devices:
                raise HTTPException(403, f"License already active on {len(devices)} device(s) (limit {user.max_devices}). "
                                         "Ask the owner to reset devices.")
            devices.append({"id": body.device_id, "name": body.device_name or "", "activated_at": datetime.now(timezone.utc).isoformat()})
        else:
            known["last_seen"] = datetime.now(timezone.utc).isoformat()
        user.devices = devices
        session.commit()
        tok = issue_license_token(user, body.device_id)
        days = (user.key_end_date.replace(tzinfo=user.key_end_date.tzinfo or timezone.utc) - datetime.now(timezone.utc)).days
        return {"status": "ok", "message": f"Welcome, {user.identifier}! {days} days remaining.", "days_remaining": days, **tok}
    # Legacy HMAC activation code (old builds)
    ok, start_s, end_s, msg = validate_legacy_code(body.license_key)
    if ok:
        now = datetime.now(timezone.utc)
        end = _dt(end_s) + timedelta(hours=23, minutes=59)
        payload = {"v": 1, "sub": body.identifier.strip() or "legacy", "uid": None, "plan": "legacy", "start": start_s,
                   "end": end_s, "device": body.device_id, "iat": now.isoformat(timespec="seconds"),
                   "offline_until": min(end, now + timedelta(days=7)).isoformat(timespec="seconds")}
        return {"status": "ok", "message": msg, "token": sign_license(payload), **payload}
    raise HTTPException(401, msg if start_s else "Invalid email or license key")


@router.post("/license/validate", tags=["license"], summary="Re-validate a license token and refresh it")
def validate(body: ValidateRequest, session: Session = Depends(get_db)):
    try:
        payload = verify_license(body.token)
    except ValueError as e:
        raise HTTPException(401, str(e))
    if payload.get("device") != body.device_id:
        raise HTTPException(401, "License token belongs to another device")
    if payload.get("uid") is None:  # legacy code token: dates are inside the signed payload
        if date.today() > date.fromisoformat(payload["end"]):
            raise HTTPException(403, f"License expired on {payload['end']}")
        now = datetime.now(timezone.utc)
        payload["iat"] = now.isoformat(timespec="seconds")
        payload["offline_until"] = (now + timedelta(days=7)).isoformat(timespec="seconds")
        return {"status": "ok", "token": sign_license(payload), **payload}
    user = session.get(User, payload["uid"])
    if not user:
        raise HTTPException(401, "License no longer exists")
    ok, msg = key_status(user)
    if not ok:
        raise HTTPException(403, msg)
    if not any(d.get("id") == body.device_id for d in (user.devices or [])):
        raise HTTPException(401, "This device was removed from the license. Activate again.")
    return {"status": "ok", **issue_license_token(user, body.device_id)}
