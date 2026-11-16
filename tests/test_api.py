from fastapi.testclient import TestClient

from backend.app.main import app


def client():
    return TestClient(app)


def test_core_endpoints():
    with client() as c:
        for path in ["/health", "/api/info", "/api/summary", "/api/board?day=2026-11-06", "/api/equity", "/api/monthly",
                     "/api/books", "/api/edge", "/api/bets?limit=5", "/api/engine", "/api/logs"]:
            r = c.get(path)
            assert r.status_code == 200, path


def test_board_has_graded_picks():
    with client() as c:
        b = c.get("/api/board?day=2026-11-06").json()
        assert len(b["games"]) == 9 and len(b["picks"]) == 8
        p = b["picks"][0]
        assert p["state"] == "graded" and p["confidence"] in "ABC" and 0 < p["breakeven"] < 1


def test_player_form_uses_only_earlier_games():
    with client() as c:
        f = c.get("/api/player?name=Alex Sarr&market=player_rebounds&before=2026-11-06").json()
        assert f["games"] and all(g["date"] < "2026-11-06" for g in f["games"])


def test_simulation():
    with client() as c:
        r = c.post("/api/simulate", json={"markets": ["totals", "h2h"], "days": 40, "sims": 500})
        assert r.status_code == 200
        s = r.json()
        assert 0 <= s["prob_profit"] <= 1 and len(s["bands"]["p50"]) == len(s["bands"]["day"])
        assert c.post("/api/simulate", json={"markets": ["nope"]}).status_code == 422


def test_exports():
    with client() as c:
        assert c.get("/api/export/picks.pdf?day=2026-11-06").content[:4] == b"%PDF"
        assert c.get("/api/export/report.pdf").content[:4] == b"%PDF"
        assert c.get("/api/export/picks.csv?day=2026-11-06").text.startswith("slate,")
        assert c.get("/api/export/bets.csv?market=h2h").text.count("\n") > 400


def test_picks_need_odds_feed():
    with client() as c:
        job = c.post("/api/engine/picks").json()["job_id"]
        import time
        for _ in range(50):
            j = c.get(f"/api/jobs/{job}").json()
            if j["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert j["status"] == "failed" and "not configured" in j["message"]
