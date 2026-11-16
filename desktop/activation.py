"""
Desktop license activation.

How it works
------------
* The owner creates a license on the server (email + key + start/end date); see
  `python -m backend.app.cli create-user`.
* On first start the user enters email + license key. The app sends them, with a hash of this
  machine's identity, to `POST /license/activate`. The server checks the dates and device limit
  and returns a license token signed with its Ed25519 **private** key.
* The app stores the token and checks it on every start with the bundled **public** key
  (`desktop/license_public_key.pem`). A public key can verify but cannot create tokens, so nobody
  can make a license from the app's files, and editing the token breaks the signature.
* The token is bound to this machine, holds the license start/end dates, and allows
  OFFLINE_GRACE days without contacting the server. Each online start refreshes it (so a
  revoked or shortened license stops working). A clock set backwards is detected.

Older HMAC activation codes still work: they are checked by the server (which holds the HMAC
secret), never in the client.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

APP_DIR_NAME = "Baseline"
CLOCK_SKEW_TOLERANCE = timedelta(hours=36)


# ---- paths -----------------------------------------------------------------------------------
def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    base = os.getenv("APPDATA") or os.path.join(Path.home(), ".config")
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def license_file() -> Path:
    return data_dir() / "license.json"


def backend_url() -> str:
    return (os.getenv("LICENSE_SERVER_URL") or os.getenv("BACKEND_API_URL") or "http://localhost:8000").rstrip("/")


# ---- device identity ---------------------------------------------------------------------------
def _machine_guid() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            return ""
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(p).read_text().strip()
        except OSError:
            pass
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        except Exception:
            pass
    return ""


def device_id() -> str:
    raw = "|".join([_machine_guid(), platform.node(), str(uuid.getnode()), platform.system()])
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def device_name() -> str:
    return f"{platform.node()} ({platform.system()} {platform.release()})"


# ---- signature verification ---------------------------------------------------------------------------
def _load_public_key():
    from cryptography.hazmat.primitives import serialization
    pem = os.getenv("LICENSE_PUBLIC_KEY", "").replace("\\n", "\n").strip()
    if not pem:
        for candidate in (_app_root() / "desktop" / "license_public_key.pem", Path(__file__).with_name("license_public_key.pem")):
            if candidate.exists():
                pem = candidate.read_text()
                break
    if not pem:
        # last resort: key pinned at first activation (trust on first use)
        stored = _read_store()
        pem = stored.get("pinned_public_key", "")
    if not pem:
        return None
    return serialization.load_pem_public_key(pem.encode())


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_token(token: str) -> Dict[str, Any]:
    """Signature check only. Raises ValueError."""
    pub = _load_public_key()
    if pub is None:
        raise ValueError("License public key is missing from this installation.")
    try:
        body_b64, sig_b64 = token.strip().split(".")
        body, sig = _unb64(body_b64), _unb64(sig_b64)
        pub.verify(sig, body)
    except Exception as e:
        raise ValueError("License file is invalid or has been modified.") from e
    return json.loads(body)


# ---- local store ---------------------------------------------------------------------------------
def _read_store() -> Dict[str, Any]:
    try:
        return json.loads(license_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_store(data: Dict[str, Any]) -> None:
    f = license_file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(f)


def clear_license() -> None:
    try:
        license_file().unlink()
    except FileNotFoundError:
        pass


def stored_credentials() -> Tuple[str, str]:
    s = _read_store()
    return s.get("identifier", ""), s.get("license_key", "")


# ---- checks -------------------------------------------------------------------------------------
def check_payload(payload: Dict[str, Any], now: Optional[datetime] = None, require_online_after: bool = True) -> Tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    if payload.get("device") != device_id():
        return False, "This license was activated on a different computer."
    today = now.date()
    start, end = date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])
    if today < start:
        return False, f"License not yet active. Starts on {start}."
    if today > end:
        return False, f"License expired on {end}."
    store = _read_store()
    last_seen = store.get("last_seen")
    if last_seen:
        ls = datetime.fromisoformat(last_seen)
        if now + CLOCK_SKEW_TOLERANCE < ls:
            return False, "The system clock appears to have been set back. Correct the date and time, then restart."
    iat = datetime.fromisoformat(payload["iat"])
    if now + CLOCK_SKEW_TOLERANCE < iat:
        return False, "The system clock is earlier than the license issue time. Correct the date and time."
    if require_online_after and now > datetime.fromisoformat(payload["offline_until"]):
        return False, "offline-period-expired"
    return True, f"License valid until {end} ({(end - today).days} days remaining)."


def _touch(payload: Dict[str, Any], token: str, **extra) -> None:
    store = _read_store()
    now = datetime.now(timezone.utc)
    prev = store.get("last_seen")
    last_seen = max(now, datetime.fromisoformat(prev)) if prev else now
    store.update({"token": token, "last_seen": last_seen.isoformat(), "end": payload["end"], "start": payload["start"],
                  "identifier": payload.get("sub", store.get("identifier", "")), **extra})
    _write_store(store)


def activate_online(identifier: str, license_key: str, timeout: int = 30) -> Tuple[bool, Dict[str, Any], str]:
    try:
        r = requests.post(f"{backend_url()}/api/license/activate", timeout=timeout, json={
            "identifier": identifier.strip(), "license_key": license_key.strip(),
            "device_id": device_id(), "device_name": device_name()})
    except requests.RequestException as e:
        logger.warning("Activation request failed: %s", e)
        return False, {}, "Could not reach the license server. Check your internet connection and try again."
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code != 200:
        return False, {}, data.get("detail") or f"Activation failed (HTTP {r.status_code})."
    token = data["token"]
    extra = {"identifier": identifier.strip(), "license_key": license_key.strip()}
    if _load_public_key() is None:
        # no bundled key: pin the server's key now
        try:
            pk = requests.get(f"{backend_url()}/api/license/public-key", timeout=timeout).json()["public_key_pem"]
            extra["pinned_public_key"] = pk
            _write_store({**_read_store(), "pinned_public_key": pk})
        except Exception:
            return False, {}, "License server did not provide a verification key."
    try:
        payload = verify_token(token)
    except ValueError as e:
        return False, {}, f"License server response could not be verified: {e}"
    ok, msg = check_payload(payload)
    if not ok:
        return False, payload, msg
    _touch(payload, token, **extra)
    return True, payload, data.get("message") or msg


def check_startup(timeout: int = 15) -> Tuple[bool, Dict[str, Any], str]:
    """Validate the stored license (refreshing it online when possible).

    Returns (ok, payload, message). ok=False with an empty payload means "ask for activation".
    """
    store = _read_store()
    token = store.get("token")
    if not token:
        return False, {}, "No license on this computer."
    try:
        payload = verify_token(token)
    except ValueError as e:
        return False, {}, str(e)
    ok, msg = check_payload(payload, require_online_after=False)
    if not ok:
        return False, payload, msg
    # try to refresh online
    try:
        r = requests.post(f"{backend_url()}/api/license/validate", json={"token": token, "device_id": device_id()}, timeout=timeout)
        if r.status_code == 200:
            new = r.json()["token"]
            new_payload = verify_token(new)
            ok, msg = check_payload(new_payload)
            if ok:
                _touch(new_payload, new)
            return ok, new_payload, msg
        if r.status_code in (401, 403):
            detail = (r.json() or {}).get("detail", "License is no longer valid.")
            clear_license_token()
            return False, {}, detail
        logger.warning("License refresh returned HTTP %s; using offline grace period", r.status_code)
    except requests.RequestException as e:
        logger.info("License server unreachable (%s); using offline grace period", e)
    ok, msg = check_payload(payload, require_online_after=True)
    if not ok and msg == "offline-period-expired":
        return False, payload, "Please connect to the internet to re-validate your license."
    if ok:
        _touch(payload, token)
    return ok, payload, msg + " (offline)"


def clear_license_token() -> None:
    store = _read_store()
    store.pop("token", None)
    _write_store(store)


def validate_activation_code(code: str) -> Tuple[bool, str, str, str]:
    """Kept for compatibility with older callers: validates any key/code via the server."""
    ident, _ = stored_credentials()
    ok, payload, msg = activate_online(ident or "legacy", code)
    return ok, payload.get("start", "N/A"), payload.get("end", "N/A"), msg
