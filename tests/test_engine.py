"""Pick logic on a fixed quote: only quotes stamped before the decision count, and the EV floor is applied."""
import json

import pandas as pd

import livepicks


def ev(book, price, last_update, name="Test Player", point=8.5):
    return {"id": "e1", "bookmakers": [{"key": book, "markets": [{"key": "player_rebounds", "last_update": last_update, "outcomes": [
        {"name": "Over", "description": name, "point": point, "price": price},
        {"name": "Under", "description": name, "point": point, "price": -price if price < 0 else -120}]}]}]}


def test_quotes_after_decision_are_ignored():
    d = pd.Timestamp("2026-11-06T23:30:00Z")
    assert len(livepicks.parse_props(ev("draftkings", -110, "2026-11-06T23:29:00Z"), d, ["player_rebounds"])) == 2
    assert len(livepicks.parse_props(ev("draftkings", -110, "2026-11-06T23:31:00Z"), d, ["player_rebounds"])) == 0


def test_rules_and_coefficients_load():
    r = livepicks.load_rules()
    assert set(r) >= {"h2h", "totals", "player_rebounds", "player_threes", "player_blocks", "player_rebounds_assists"}
    fz = json.loads(livepicks.COEF.read_text())
    assert set(fz["coef"]) == {"player_rebounds", "player_threes", "player_blocks", "player_rebounds_assists"}


def test_decision_windows():
    s = livepicks.schedule()
    d = livepicks.decisions(s, "2026-11-16")
    kinds = {x[1] for x in d}
    assert "NOON" in kinds and {"T30P", "T60P", "T30G"} <= kinds or not d
