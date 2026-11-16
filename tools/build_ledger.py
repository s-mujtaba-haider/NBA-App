"""Builds data/ledger/bets.parquet: every graded bet of the six WINNER markets in 2024-25 and 2025-26, with pick details.

Source: the NBA research repo (path as the first argument). Same selection as the Two-Season Test engine
(expansion grid, all-books set B0, two void corrections), then checked against winners.csv so the app shows
exactly the figures of record.

    python tools/build_ledger.py <path-to-NBA-repo>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parents[1]
MARKETS = ["totals", "player_rebounds", "player_threes", "player_rebounds_assists", "player_blocks", "h2h"]
VOID = {"2025-03-17": "Steven Adams", "2025-03-29": "Jaylin Williams"}


def main(src: Path):
    eg = pd.read_parquet(src / "out/expansion_grid_bets.parquet")
    eg = eg[(eg.book_set == "B0") & eg.market.isin(MARKETS) & eg.season.isin(["2024-25", "2025-26"])].copy()
    eg["slate"] = eg.slate.astype(str)
    drop = np.array([m == "player_rebounds" and VOID.get(s) == p for m, s, p in zip(eg.market, eg.slate, eg.player)])
    assert drop.sum() == 2
    eg = eg[~drop].dropna(subset=["profit"])
    again = np.where(eg.result > 0, eg.dec - 1, np.where(eg.result < 0, -1.0, 0.0))
    assert np.allclose(again, eg.profit)
    win = pd.read_csv(APP / "data/ledger/winners.csv").set_index("market")
    for m, g in eg.groupby("market"):
        assert len(g) == win.loc[m, "bets"], (m, len(g), win.loc[m, "bets"])
        assert abs(g.profit.mean() - win.loc[m, "roi"]) < 1e-9, m
    out = eg[["market", "season", "slate", "event_id", "book", "player", "side", "point", "dec", "ev", "result", "profit"]]
    out = out.sort_values(["slate", "market"]).reset_index(drop=True)
    out.to_parquet(APP / "data/ledger/bets.parquet", index=False)
    print("bets", len(out), json.dumps(out.groupby("market").profit.agg(["size", "mean"]).round(4).to_dict()))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\mujta\nba"))
