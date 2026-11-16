"""Free NBA results from stats.nba.com via nba_api (no Odds API). Resumable: a season already on disk is skipped.

Outputs (data/results/):
  schedule_{season}.parquet   game id, UTC tip time, ET slate date, teams, status, postponed flag
  player_logs_{season}.parquet  per-player box score (settlement for props; DNP = absent row)
  team_logs_{season}.parquet    per-team box score (settlement for moneyline/spread/total)
Usage: python scripts/fetch_results.py [2023-24 2024-25 ...] [--refresh-current]
"""
import sys
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, scheduleleaguev2

OUT = Path(__file__).resolve().parents[1] / "data" / "results"
OUT.mkdir(parents=True, exist_ok=True)
SEASONS = ["2023-24", "2024-25", "2025-26", "2026-27"]
TYPES = ["Regular Season", "PlayIn", "Playoffs"]


def _call(fn, tries=4):
    for a in range(tries):
        try:
            return fn()
        except Exception as e:                                   # noqa: BLE001
            print("  retry", a + 1, type(e).__name__, str(e)[:80])
            time.sleep(5 * (a + 1))
    raise RuntimeError("stats.nba.com unavailable")


def schedule(season):
    d = _call(lambda: scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=60).get_data_frames()[0])
    keep = ["gameId", "gameDateTimeUTC", "gameDateEst", "gameStatus", "gameStatusText", "postponedStatus",
            "gameLabel", "gameSubtype", "isNeutral", "homeTeam_teamId", "homeTeam_teamTricode", "homeTeam_teamCity",
            "homeTeam_teamName", "homeTeam_score", "awayTeam_teamId", "awayTeam_teamTricode", "awayTeam_teamCity",
            "awayTeam_teamName", "awayTeam_score"]
    d = d[[c for c in keep if c in d.columns]].copy()
    d["tip_utc"] = pd.to_datetime(d["gameDateTimeUTC"], utc=True)
    d["slate_date_et"] = d["tip_utc"].dt.tz_convert("America/New_York").dt.date.astype(str)
    d["season"] = season
    return d[d["gameId"].str[2] != "1"]                          # drop preseason (game id 001...)


def logs(season, kind):
    frames = []
    for st in TYPES:
        f = _call(lambda: leaguegamelog.LeagueGameLog(season=season, season_type_all_star=st,
                                                     player_or_team_abbreviation=kind, timeout=60).get_data_frames()[0])
        f["season_type"] = st
        frames.append(f)
        time.sleep(1.0)
    d = pd.concat(frames, ignore_index=True)
    d["season"] = season
    return d


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    refresh = "--refresh-current" in sys.argv
    for s in args or SEASONS:
        for name, fn in [("schedule", lambda: schedule(s)), ("player_logs", lambda: logs(s, "P")),
                         ("team_logs", lambda: logs(s, "T"))]:
            fp = OUT / f"{name}_{s}.parquet"
            if fp.exists() and not (refresh and s == SEASONS[-1]):
                continue
            d = fn()
            d.to_parquet(fp, index=False)
            print(s, name, d.shape)
            time.sleep(1.0)


if __name__ == "__main__":
    main()
