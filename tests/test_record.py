"""The app must show exactly the figures of record (data/ledger/result.json, from the research repo)."""
import json

from backend.app import record
from backend.app.config import LEDGER_DIR

RESULT = json.loads((LEDGER_DIR / "result.json").read_text(encoding="utf-8"))


def test_six_winners_match_rule_of_record():
    s = record.summary()
    assert s["winners"] == 6
    for m in s["markets"]:
        ref = RESULT["per_market"][m["key"]]
        assert m["two_season"]["bets"] == ref["bets"]
        assert abs(m["two_season"]["roi"] - ref["roi"]) < 1e-9
        assert abs(m["two_season"]["ci_low"] - ref["ci_low"]) < 1e-9


def test_2025_26_totals():
    t = record.summary()["totals"]["season_2025_26"]
    ref = RESULT["season_2025_26"]
    assert t["bets"] == ref["bets"] and t["won"] == ref["won"]
    assert abs(t["units"] - ref["units"]) < 0.01
    assert t["months_profit"] == ref["months_profit"] and t["months"] == ref["months"]


def test_profit_matches_price_and_result():
    d = record.all_bets()
    again = (d.result > 0) * (d.dec - 1) - (d.result < 0) * 1.0
    assert (abs(again - d.profit) < 1e-9).all()


def test_american_odds():
    assert list(record.american([2.5, 1.5, 2.0])) == [150, -200, 100]
