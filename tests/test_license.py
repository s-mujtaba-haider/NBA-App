from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import verify_license

ADMIN = {"X-Admin-Token": "test-admin"}


def test_license_lifecycle():
    with TestClient(app) as c:
        assert c.post("/api/admin/users", json={"identifier": "x@y.z", "days": 30}).status_code == 403
        r = c.post("/api/admin/users", json={"identifier": "owner@example.com", "days": 30, "max_devices": 1}, headers=ADMIN)
        assert r.status_code == 200
        key, uid = r.json()["api_key"], r.json()["id"]
        assert c.post("/api/login", json={"identifier": "owner@example.com", "api_key": key}).status_code == 200
        assert c.post("/api/login", json={"identifier": "owner@example.com", "api_key": "WRONG"}).status_code == 401
        a = c.post("/api/license/activate", json={"identifier": "owner@example.com", "license_key": key, "device_id": "device-0001"})
        assert a.status_code == 200
        tok = a.json()["token"]
        assert verify_license(tok)["device"] == "device-0001"
        # device limit
        assert c.post("/api/license/activate", json={"identifier": "owner@example.com", "license_key": key, "device_id": "device-0002"}).status_code == 403
        # tampering breaks the signature
        body, sig = tok.split(".")
        assert c.post("/api/license/validate", json={"token": body[:-2] + "AA." + sig, "device_id": "device-0001"}).status_code == 401
        assert c.post("/api/license/validate", json={"token": tok, "device_id": "device-0001"}).status_code == 200
        # expired license is blocked
        c.patch(f"/api/admin/users/{uid}", json={"end_date": "2020-01-01"}, headers=ADMIN)
        assert c.post("/api/license/validate", json={"token": tok, "device_id": "device-0001"}).status_code == 403
