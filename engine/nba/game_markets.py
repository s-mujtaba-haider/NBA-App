"""Point-in-time game-market quotes (moneyline, spread, total) from cached Stage 1 snapshots, joined to settled games.

Rules (NBA_REQUIREMENTS.md R4, R10, R14, A10, A13):
  * A snapshot is requested at the decision time D. A quote counts only if its market `last_update` <= D.
  * Today's games only: the game's ET slate date must equal the snapshot's slate date. For T-x windows only the games
    whose scheduled tip equals the tip slot are taken (each game is priced x minutes before its own tip).
  * Games already started at D (commence_time <= D) are dropped.
  * Bet prices come from the scope books only; Pinnacle is a fair-price reference, never a bet price.
  * Settlement uses the final score (overtime included). A game that never reached Final is void.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

from nba import oddsapi_gate as gate
from nba.scope_gate import SCOPE_KEYS, WINDOWS, american_to_decimal

ROOT = Path(os.environ.get("BASELINE_HOME") or Path(__file__).resolve().parents[2])
PATH = "/v4/historical/sports/basketball_nba/odds"
BOOKS = "betmgm,betrivers,draftkings,espnbet,fanatics,fanduel,hardrockbet,pinnacle,williamhill_us"
FIXED = dict(markets="h2h,spreads,totals", bookmakers=BOOKS, oddsFormat="american", dateFormat="iso")
SEASONS = ["2023-24", "2024-25", "2025-26"]

# Odds API team name -> nba_api tricode (the schedule spells the Clippers "LA Clippers").
TEAM_ALIASES = {"Los Angeles Clippers": "LAC", "LA Clippers": "LAC"}


def load_schedule(seasons=SEASONS) -> pd.DataFrame:
    d = pd.concat([pd.read_parquet(f) for s in seasons for f in glob.glob(str(ROOT / f"data/results/schedule_{s}.parquet"))])
    teams = set(d[d.gameId.str.startswith("002")].homeTeam_teamTricode)           # the 30 franchises (regular season)
    d = d[d.homeTeam_teamTricode.isin(teams) & d.awayTeam_teamTricode.isin(teams)].copy()  # drop All-Star / Rising Stars
    d["home_name"] = d.homeTeam_teamCity + " " + d.homeTeam_teamName
    d["away_name"] = d.awayTeam_teamCity + " " + d.awayTeam_teamName
    return d


def team_codes(sched: pd.DataFrame) -> dict:
    m = dict(zip(sched.home_name, sched.homeTeam_teamTricode))
    m.update(zip(sched.away_name, sched.awayTeam_teamTricode))
    m.update(TEAM_ALIASES)
    return m


def snapshot_plan(sched: pd.DataFrame) -> pd.DataFrame:
    """One row per (window, slate, decision time, tip slot). tip is NaT for clock windows (all of today's games)."""
    fin = sched[sched.gameStatus == 3]
    rows = []
    for day, g in fin.groupby("slate_date_et"):
        for w, (kind, v) in WINDOWS.items():
            if kind == "clock":
                rows.append((w, day, pd.Timestamp(f"{day} {v}", tz="America/New_York").tz_convert("UTC"), pd.NaT))
            else:
                for tip in sorted(g.tip_utc.unique()):
                    rows.append((w, day, pd.Timestamp(tip) - pd.Timedelta(minutes=v), pd.Timestamp(tip)))
    s = pd.DataFrame(rows, columns=["window", "slate", "decision", "tip_slot"])
    s["date"] = s.decision.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return s


COLUMNS = ["window", "slate", "decision", "game_id", "season", "game_status", "tip_utc",
           "home_score", "away_score", "book", "market", "side", "point", "price", "last_update"]


def event_quotes(ev: dict, window, slate, decision, tip_slot, by_key: dict, codes: dict, stats: dict) -> list:
    """Point-in-time quote rows (COLUMNS order) for one API event at one decision time; counts drops in stats.
    Shared by the historical backtest (quotes) and the live forward test."""
    rows = []
    stats["events_seen"] += 1
    tip = pd.Timestamp(ev["commence_time"])
    if tip.tz_convert("America/New_York").strftime("%Y-%m-%d") != slate:
        stats["other_day"] += 1
        return rows
    h, a = codes.get(ev["home_team"]), codes.get(ev["away_team"])
    g = by_key.get((slate, h, a))
    if g is None:
        stats["unmatched_team"] += 1
        return rows
    if pd.notna(tip_slot) and g.tip_utc != tip_slot:
        stats["other_tip"] += 1
        return rows
    if tip <= decision or g.tip_utc <= decision:
        stats["started"] += 1
        return rows
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if pd.Timestamp(mk["last_update"]) > decision:
                stats["quotes_after_decision"] += len(mk["outcomes"])
                continue
            for o in mk["outcomes"]:
                if mk["key"] == "totals":
                    side = o["name"].lower()
                else:
                    side = "home" if o["name"] == ev["home_team"] else "away" if o["name"] == ev["away_team"] else None
                if side is None:
                    continue
                rows.append((window, slate, decision, g.gameId, g.season, g.gameStatus, g.tip_utc,
                             g.homeTeam_score, g.awayTeam_score, bk["key"], mk["key"], side,
                             o.get("point", np.nan), o["price"], mk["last_update"]))
    return rows


def finish_quotes(out: list) -> pd.DataFrame:
    q = pd.DataFrame(out, columns=COLUMNS)
    q = q.drop_duplicates(["window", "game_id", "book", "market", "side"])
    q["dec"] = american_to_decimal(q.price)
    q["is_scope"] = q.book.isin(SCOPE_KEYS)
    return q


def quotes(seasons=SEASONS, sched: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Long table of eligible point-in-time quotes: one row per window x game x book x market x side.
    Returns (quotes, stats) where stats counts dropped records for the audit."""
    sched = load_schedule(seasons) if sched is None else sched
    codes = team_codes(sched)
    by_key = {(r.slate_date_et, r.homeTeam_teamTricode, r.awayTeam_teamTricode): r for r in sched.itertuples()}
    plan = snapshot_plan(sched)
    stats = dict(snapshots=len(plan), missing_snapshot=0, events_seen=0, other_day=0, other_tip=0, started=0,
                 unmatched_team=0, quotes_after_decision=0, quotes_kept=0)
    out = []
    for p in plan.itertuples():
        data = gate.cached(PATH, {**FIXED, "date": p.date})
        if data is None:
            stats["missing_snapshot"] += 1
            continue
        for ev in data.get("data", []):
            out.extend(event_quotes(ev, p.window, p.slate, p.decision, p.tip_slot, by_key, codes, stats))
    q = finish_quotes(out)
    stats["quotes_kept"] = len(q)
    return q, stats


def grade(market: str, side: str, point: float, home: int, away: int, final: bool) -> float:
    """+1 win, -1 loss, 0 push, NaN void. Spread point is the handicap applied to the side's own score."""
    if not final:
        return np.nan
    if market == "h2h":
        diff = home - away if side == "home" else away - home
        return float(np.sign(diff))
    if market == "spreads":
        diff = (home - away if side == "home" else away - home) + point
        return float(np.sign(diff))
    if market == "totals":
        diff = (home + away) - point
        return float(np.sign(diff) if side == "over" else -np.sign(diff))
    raise ValueError(market)
