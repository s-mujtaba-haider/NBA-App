"""API keys, admin auth, and signed license tokens.

* API keys are stored as SHA-256 hashes; the plain key is shown once when created or rotated.
* Admin endpoints need `X-Admin-Token` (ADMIN_TOKEN) or the API key of a user with role=admin.
* License tokens are signed with an Ed25519 private key that only the server holds. Desktop
  builds ship only the public key, so they can verify a license offline but cannot create one.
* Legacy HMAC activation codes (old desktop builds) are checked here, server side, so the HMAC
  secret no longer has to live in the client.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR, settings
from .db import User, get_db

logger = logging.getLogger("security")

TOKEN_VERSION = 1
OFFLINE_GRACE_DAYS = 7


# ---- API keys --------------------------------------------------------------------------------
def hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode()).hexdigest()


def generate_api_key() -> str:
    """License/API key in the XXXX-XXXX-XXXX-XXXX-XXXX format shown in the desktop dialog."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(20))
    return "-".join(raw[i:i + 4] for i in range(0, 20, 4))


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def user_by_key(session: Session, key: str) -> Optional[User]:
    if not key:
        return None
    return session.execute(select(User).where(User.api_key_hash == hash_key(key))).scalar_one_or_none()


def key_status(user: User) -> Tuple[bool, str]:
    now = datetime.now(timezone.utc)
    if not user.is_active:
        return False, "This account has been deactivated."
    if now < _aware(user.key_start_date):
        return False, f"License not yet active. Starts on {_aware(user.key_start_date):%Y-%m-%d}."
    if now > _aware(user.key_end_date):
        return False, f"License expired on {_aware(user.key_end_date):%Y-%m-%d}."
    return True, "ok"


def current_user(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
                 session: Session = Depends(get_db)) -> User:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    user = user_by_key(session, x_api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    ok, msg = key_status(user)
    if not ok:
        raise HTTPException(status_code=403, detail=msg)
    return user


def optional_user(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
                  session: Session = Depends(get_db)) -> Optional[User]:
    """Used by data endpoints: only enforced when REQUIRE_API_KEY=true."""
    if not settings.require_api_key:
        return user_by_key(session, x_api_key) if x_api_key else None
    return current_user(x_api_key, session)


def require_admin(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
                  x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
                  session: Session = Depends(get_db)) -> str:
    if settings.admin_token and x_admin_token and hmac.compare_digest(settings.admin_token, x_admin_token):
        return "admin-token"
    if x_api_key:
        user = user_by_key(session, x_api_key)
        if user and user.role == "admin" and key_status(user)[0]:
            return user.identifier
    raise HTTPException(status_code=403, detail="Admin credentials required (X-Admin-Token or an admin API key)")


# ---- Ed25519 license signing ---------------------------------------------------------------------
_private_key: Optional[Ed25519PrivateKey] = None


def _key_file():
    return DATA_DIR / "license_private_key.pem"


def private_key() -> Ed25519PrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key
    raw = settings.license_private_key.strip()
    if raw:
        if "BEGIN" in raw:
            _private_key = serialization.load_pem_private_key(raw.replace("\\n", "\n").encode(), password=None)
        else:
            _private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))
    else:
        f = _key_file()
        if f.exists():
            _private_key = serialization.load_pem_private_key(f.read_bytes(), password=None)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            _private_key = Ed25519PrivateKey.generate()
            f.write_bytes(_private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
            logger.warning("LICENSE_PRIVATE_KEY not set: generated a new signing key at %s. Set LICENSE_PRIVATE_KEY in "
                           "production and ship the matching public key with the desktop app.", f)
    return _private_key


def public_key_pem() -> str:
    return private_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_license(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = private_key().sign(body)
    return f"{_b64(body)}.{_b64(sig)}"


def verify_license(token: str, public: Optional[Ed25519PublicKey] = None) -> Dict[str, Any]:
    """Raises ValueError on a bad signature; returns the payload otherwise (dates not checked)."""
    try:
        body_b64, sig_b64 = token.strip().split(".")
        body, sig = _unb64(body_b64), _unb64(sig_b64)
    except Exception as e:
        raise ValueError("Malformed license token") from e
    pub = public or private_key().public_key()
    try:
        pub.verify(sig, body)
    except Exception as e:
        raise ValueError("Invalid license signature") from e
    return json.loads(body)


def issue_license_token(user: User, device_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start, end = _aware(user.key_start_date), _aware(user.key_end_date)
    payload = {
        "v": TOKEN_VERSION, "sub": user.identifier, "uid": user.id, "plan": user.plan,
        "start": start.date().isoformat(), "end": end.date().isoformat(),
        "device": device_id, "iat": now.isoformat(timespec="seconds"),
        "offline_until": min(end, now + timedelta(days=OFFLINE_GRACE_DAYS)).isoformat(timespec="seconds"),
    }
    return {"token": sign_license(payload), **payload}


# ---- legacy HMAC activation codes ------------------------------------------------------------------
def validate_legacy_code(code: str) -> Tuple[bool, str, str, str]:
    """Same format as the old src/activation.py; secret comes from LEGACY_HMAC_SECRET."""
    secret = settings.legacy_hmac_secret.encode()
    if not secret:
        return False, "", "", "Legacy activation codes are not enabled on this server."
    try:
        code = code.strip()
        decoded = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode()
        start_s, end_s, sig_b64 = decoded.split("|")
        expected = hmac.new(secret, f"{settings.legacy_hmac_user_id}|{start_s}|{end_s}".encode(), hashlib.sha256).digest()
        received = base64.b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(expected, received):
            return False, "", "", "Invalid activation code."
        start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
        today = date.today()
        if today < start:
            return False, start_s, end_s, f"License not yet active. Starts on {start_s}."
        if today > end:
            return False, start_s, end_s, f"License expired on {end_s}."
        return True, start_s, end_s, f"License is valid until {end_s}."
    except Exception:
        return False, "", "", "Invalid activation code."


def make_legacy_code(start_s: str, end_s: str) -> str:
    """Owner-side generator for legacy-format codes (requires LEGACY_HMAC_SECRET)."""
    secret = settings.legacy_hmac_secret.encode()
    if not secret:
        raise ValueError("LEGACY_HMAC_SECRET is not set")
    sig = hmac.new(secret, f"{settings.legacy_hmac_user_id}|{start_s}|{end_s}".encode(), hashlib.sha256).digest()
    combined = f"{start_s}|{end_s}|{base64.b64encode(sig).decode()}"
    return base64.urlsafe_b64encode(combined.encode()).decode().rstrip("=")
