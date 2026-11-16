"""Point-in-time team model for game markets (candidate strategy 3, NBA_RESEARCH_PLAN.md §3).

* Margin: Elo with margin-of-victory multiplier (FiveThirtyEight NBA form), home advantage HCA Elo points, 25% regression
  to the mean between seasons, plus a rest adjustment (back-to-back / days of rest) estimated on discovery seasons.
  Predicted home margin = (elo_home + HCA - elo_away) / ELO_PER_POINT + rest terms.
* Total: EWMA of each team's points scored and allowed in previous games -> expected total.
Every value for a game is computed from games strictly before it (ratings are updated after the game is recorded).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

K, HCA, ELO_PER_POINT, CARRY = 20.0, 70.0, 28.0, 0.75
HL_TOTAL = 10


def game_table(sched: pd.DataFrame) -> pd.DataFrame:
    g = sched[sched.gameStatus == 3].sort_values(["tip_utc", "gameId"]).reset_index(drop=True)
    return g[["gameId", "season", "slate_date_et", "tip_utc", "homeTeam_teamTricode", "awayTeam_teamTricode",
              "homeTeam_score", "awayTeam_score"]].rename(columns={
        "homeTeam_teamTricode": "home", "awayTeam_teamTricode": "away", "homeTeam_score": "hs", "awayTeam_score": "as_"})


def elo_and_rest(g: pd.DataFrame) -> pd.DataFrame:
    elo, last_date, season_of = {}, {}, {}
    rows = []
    for r in g.itertuples():
        d = pd.Timestamp(r.slate_date_et)
        for t in (r.home, r.away):
            if t not in elo:
                elo[t] = 1500.0
            if season_of.get(t) not in (None, r.season):               # new season: regress toward the mean
                elo[t] = CARRY * elo[t] + (1 - CARRY) * 1505.0
            season_of[t] = r.season
        rest = {t: min((d - last_date[t]).days - 1, 4) if t in last_date and season_of.get(t) == r.season else 4
                for t in (r.home, r.away)}
        eh, ea = elo[r.home], elo[r.away]
        rows.append(dict(gameId=r.gameId, elo_home=eh, elo_away=ea, rest_home=rest[r.home], rest_away=rest[r.away],
                         b2b_home=int(rest[r.home] == 0), b2b_away=int(rest[r.away] == 0)))
        # update after the game
        diff = eh + HCA - ea
        exp_h = 1 / (1 + 10 ** (-diff / 400))
        mov = r.hs - r.as_
        mult = (abs(mov) + 3) ** 0.8 / (7.5 + 0.006 * (diff if mov > 0 else -diff))
        delta = K * mult * ((1.0 if mov > 0 else 0.0) - exp_h)
        elo[r.home], elo[r.away] = eh + delta, ea - delta
        last_date[r.home] = last_date[r.away] = d
    return g.merge(pd.DataFrame(rows), on="gameId")


def scoring_form(g: pd.DataFrame) -> pd.DataFrame:
    long = pd.concat([
        g[["gameId", "tip_utc", "home", "hs", "as_"]].rename(columns={"home": "team", "hs": "pf", "as_": "pa"}),
        g[["gameId", "tip_utc", "away", "as_", "hs"]].rename(columns={"away": "team", "as_": "pf", "hs": "pa"}),
    ]).sort_values(["team", "tip_utc"])
    grp = long.groupby("team")
    long["pf_ewm"] = grp.pf.transform(lambda s: s.shift(1).ewm(halflife=HL_TOTAL, min_periods=3).mean())
    long["pa_ewm"] = grp.pa.transform(lambda s: s.shift(1).ewm(halflife=HL_TOTAL, min_periods=3).mean())
    h = long.set_index(["gameId", "team"])[["pf_ewm", "pa_ewm"]]
    out = g.join(h, on=["gameId", "home"]).join(h, on=["gameId", "away"], rsuffix="_a")
    out["model_total"] = (out.pf_ewm + out.pa_ewm_a + out.pf_ewm_a + out.pa_ewm) / 2
    return out


def build(sched: pd.DataFrame, rest_coef: dict | None = None) -> pd.DataFrame:
    g = scoring_form(elo_and_rest(game_table(sched)))
    g["model_margin_elo"] = (g.elo_home + HCA - g.elo_away) / ELO_PER_POINT
    rc = rest_coef or {"b2b_home": 0.0, "b2b_away": 0.0}
    g["model_margin"] = g.model_margin_elo + rc["b2b_home"] * g.b2b_home + rc["b2b_away"] * g.b2b_away
    g["margin"] = g.hs - g.as_
    g["total"] = g.hs + g.as_
    return g


def fit_rest(g: pd.DataFrame, seasons) -> dict:
    """OLS of the Elo residual on back-to-back flags, discovery seasons only."""
    d = g[g.season.isin(seasons)]
    X = np.column_stack([d.b2b_home, d.b2b_away, np.ones(len(d))])
    beta, *_ = np.linalg.lstsq(X, d.margin - d.model_margin_elo, rcond=None)
    return {"b2b_home": float(beta[0]), "b2b_away": float(beta[1]), "intercept": float(beta[2])}
