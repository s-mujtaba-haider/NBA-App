"""Point-in-time player projections for prop markets (candidate strategy 2, NBA_RESEARCH_PLAN.md §3).

For every player-game the projection uses ONLY games with an earlier date (no same-day information):
  * expected minutes = EWMA of the player's minutes in previous games (half-life HL_MIN games),
  * per-minute rate of each stat = EWMA over previous games, shrunk toward the league per-minute rate with weight
    PRIOR_MIN minutes (stabilises small samples),
  * mean = expected minutes x rate. Counts (REB, AST, FG3M, STL, BLK, TOV) -> negative binomial with a per-stat dispersion
    fitted on the discovery seasons; PTS and PRA -> normal with SD proportional to sqrt(mean) (fitted on discovery).
History carries across seasons (a player's previous season seeds the next), which is information available before tip.
Known limit: the projection does not know tonight's injuries or role changes; the market price does. That is why the model
is only used blended with the market price (stacking fitted on discovery), never alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import nbinom, norm

STATS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "PRA"]
COUNT_STATS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "PRA"]   # all counts; PTS/PRA are right-skewed (normal overstated overs ~5pp on discovery)
HL_MIN, HL_RATE, PRIOR_MIN = 8, 15, 120.0


def build_projections(box: pd.DataFrame) -> pd.DataFrame:
    """box: player game logs (all seasons). Returns one row per player-game with proj_min and proj_<STAT> (pre-game)."""
    b = box.copy()
    b["PRA"] = b.PTS + b.REB + b.AST
    b["date"] = pd.to_datetime(b.GAME_DATE)
    b = b.sort_values(["PLAYER_ID", "date", "GAME_ID"]).reset_index(drop=True)
    g = b.groupby("PLAYER_ID", sort=False)
    # expected minutes: EWMA of previous games' minutes (shift(1) => strictly earlier games)
    b["proj_min"] = g.MIN.transform(lambda s: s.shift(1).ewm(halflife=HL_MIN, min_periods=1).mean())
    b["n_prev"] = g.cumcount()
    # league per-minute rates from earlier dates only (expanding, by date)
    daily = b.groupby("date")[STATS + ["MIN"]].sum().sort_index()
    league = daily[STATS].cumsum().shift(1).div(daily.MIN.cumsum().shift(1), axis=0)
    for s in STATS:
        lr = b.date.map(league[s])
        # EWMA of stat and minutes with the same weights -> rate = ewm(stat)/ewm(min); shrink toward league rate
        num = g[s].transform(lambda x: x.shift(1).ewm(halflife=HL_RATE, min_periods=1).mean())
        den = g.MIN.transform(lambda x: x.shift(1).ewm(halflife=HL_RATE, min_periods=1).mean())
        w = np.minimum(b.n_prev, 3 * HL_RATE) * den                    # effective minutes behind the EWMA
        rate = (num / den.replace(0, np.nan) * w + lr * PRIOR_MIN) / (w + PRIOR_MIN)
        b[f"proj_{s}"] = rate * b.proj_min
    return b


def fit_dispersion(p: pd.DataFrame, seasons) -> dict:
    """Per stat: NB size r (counts) or normal SD scale k with SD = k*sqrt(mean), method of moments on discovery seasons."""
    d = p[p.season.isin(seasons) & (p.n_prev >= 5)]
    out = {}
    for s in STATS:
        mu, y = d[f"proj_{s}"], d[s]
        ok = mu.notna() & (mu > 0.05)
        mu, y = mu[ok], y[ok]
        if s in COUNT_STATS:
            # Var = mu + mu^2/r  ->  r = sum(mu^2) / sum((y-mu)^2 - mu)
            excess = ((y - mu) ** 2 - mu).sum()
            out[s] = ("nb", float((mu ** 2).sum() / excess) if excess > 0 else 1e6)
        else:
            out[s] = ("normal", float(np.sqrt(((y - mu) ** 2).sum() / mu.sum())))
    return out


def p_over(stat: str, mean, line, disp: dict):
    """P(stat > line) and P(stat == line) (push, integer lines) under the fitted distribution."""
    mean, line = np.asarray(mean, float), np.asarray(line, float)
    kind, par = disp[stat]
    if kind == "nb":
        r = par
        pr = r / (r + np.maximum(mean, 1e-6))
        over = nbinom.sf(np.floor(line), r, pr)
        push = np.where(np.isclose(line, np.round(line)), nbinom.pmf(np.round(line), r, pr), 0.0)
    else:
        sd = par * np.sqrt(np.maximum(mean, 1e-6))
        is_int = np.isclose(line, np.round(line))
        over = 1 - norm.cdf((np.where(is_int, line + 0.5, line) - mean) / sd)
        push = np.where(is_int, norm.cdf((line + 0.5 - mean) / sd) - norm.cdf((line - 0.5 - mean) / sd), 0.0)
    return over, push
