"""The six WINNER markets and how each one picks (frozen rules, data/rules/)."""
from __future__ import annotations

MARKETS = {
    "totals": dict(label="Game Totals", short="TOT", kind="game", window="T-30", window_key="T30",
                   stat=None, rule="Pinnacle no-vig fair line on a fitted total; best price across 8 books; EV >= 0",
                   rule_name="totals T-30"),
    "player_rebounds": dict(label="Player Rebounds", short="REB", kind="prop", window="T-30", window_key="T30",
                            stat="REB", rule="Market fair price stacked with the player projection model; EV >= 10%",
                            rule_name="rebounds T-30"),
    "player_threes": dict(label="Player Threes", short="3PM", kind="prop", window="T-60", window_key="T60",
                          stat="FG3M", rule="Market fair price stacked with the player projection model; EV >= 10%",
                          rule_name="threes T-60"),
    "player_rebounds_assists": dict(label="Rebounds + Assists", short="R+A", kind="prop", window="T-30", window_key="T30",
                                    stat="RA", rule="Market fair price stacked with a combined REB+AST model; EV >= 7.5%",
                                    rule_name="rebounds+assists T-30"),
    "player_blocks": dict(label="Player Blocks", short="BLK", kind="prop", window="T-60", window_key="T60",
                          stat="BLK", rule="Market fair price stacked with the player projection model; EV >= 7.5%",
                          rule_name="blocks T-60"),
    "h2h": dict(label="Moneyline", short="ML", kind="game", window="12:00 ET", window_key="NOON",
                stat=None, rule="Pinnacle no-vig (power method) fair price; best price across 8 books; EV >= 0",
                rule_name="moneyline NOON"),
}
ORDER = list(MARKETS)
RULE_TO_MARKET = {v["rule_name"]: k for k, v in MARKETS.items()}

BOOKS = {"betmgm": "BetMGM", "betrivers": "BetRivers", "draftkings": "DraftKings", "espnbet": "ESPN BET",
         "fanatics": "Fanatics", "fanduel": "FanDuel", "hardrockbet": "Hard Rock", "williamhill_us": "Caesars"}

RULE_OF_RECORD = {
    "name": "Two-Season Test",
    "definition": "ROI >= +3% and 95% CI lower bound > 0 over 2024-25 + 2025-26, and ROI >= +3% on 2025-26 alone",
    "disclosure": [
        "The rule was chosen after the results were known; it adds no evidence by itself.",
        "Strict count (ROI >= +3% and CI lower bound > 0 on 2025-26 alone) is 3 markets.",
        "Moneyline passes with a CI lower bound of only +0.1% and falls below 0 once live 2026-27 bets are added.",
        "Past results do not guarantee future results. The live record decides what holds up.",
    ],
}
