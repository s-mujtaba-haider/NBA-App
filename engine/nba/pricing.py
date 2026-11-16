"""Fair prices and expected value for NBA game markets (moneyline, spread, total).

Fair reference: Pinnacle's no-vig price in the same snapshot. If Pinnacle has no quote, the median of the other scope
books (leave-one-out: the book being priced is excluded from its own reference).

Spreads and totals: books hang different lines, so a fair probability is needed at every line. The outcome (home margin
or game total, both integers) is modelled as Normal(mu, sigma) with a continuity correction:
  * mu is solved so the model reproduces the reference book's no-vig cover probability at its own line,
  * sigma is a market constant estimated on the discovery seasons only (`estimate_sigma`),
  * integer lines carry a push probability; half lines do not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from nba.scope_gate import no_vig_two_way

DISCOVERY = ["2023-24", "2024-25"]
HOLDOUT = ["2025-26"]


def win_push(mu, line, sigma, market, side):
    """P(win), P(push) for one side. spreads: side's handicap `line`; totals: the total line."""
    mu, line = np.asarray(mu, float), np.asarray(line, float)
    if market == "spreads":
        # home covers iff M + L > 0 with M = home margin; away covers iff -M + L > 0.
        thr = -line if side == "home" else line          # home wins iff M > thr; away wins iff M < thr
    else:
        thr = line                                        # over wins iff T > thr; under wins iff T < thr
    is_int = np.isclose(thr, np.round(thr))
    up = np.where(is_int, thr + 0.5, thr)                 # P(X > thr) with X integer
    dn = np.where(is_int, thr - 0.5, thr)                 # P(X < thr)
    p_above = 1 - norm.cdf((up - mu) / sigma)
    p_below = norm.cdf((dn - mu) / sigma)
    p_push = np.where(is_int, 1 - p_above - p_below, 0.0)
    above_wins = (market == "spreads" and side == "home") or (market == "totals" and side == "over")
    return (p_above if above_wins else p_below), p_push


def solve_mu(p_fair_cover, line, sigma, market, side, lo=-80.0, hi=320.0):
    """mu so that P(win)/(P(win)+P(loss)) equals the no-vig cover probability at `line` (vectorised bisection)."""
    p = np.asarray(p_fair_cover, float)
    line = np.asarray(line, float)
    lo = np.full_like(p, lo)
    hi = np.full_like(p, hi)
    rising = (market == "spreads" and side == "home") or (market == "totals" and side == "over")
    for _ in range(70):
        mid = (lo + hi) / 2
        w, pu = win_push(mid, line, sigma, market, side)
        c = w / np.maximum(1 - pu, 1e-12)
        go_up = (c < p) if rising else (c > p)
        lo, hi = np.where(go_up, mid, lo), np.where(go_up, hi, mid)
    return (lo + hi) / 2


def two_way(q: pd.DataFrame, devig: str = "multiplicative") -> pd.DataFrame:
    """Pair the two sides of each (window, game, book, market). Spreads/totals need both sides on the same line.
    devig: 'multiplicative' (proportional) or 'power' (shrinks longshots; the proportional method is known to overstate
    longshot probability, which shows up as false +EV on big moneyline underdogs)."""
    a_side = {"h2h": "home", "spreads": "home", "totals": "over"}
    q = q.copy()
    q["is_a"] = [s == a_side[m] for s, m in zip(q.side, q.market)]
    k = ["window", "game_id", "book", "market"]
    a = q[q.is_a].set_index(k)
    b = q[~q.is_a].set_index(k)
    j = a.join(b[["side", "point", "price", "dec"]], rsuffix="_b", how="inner")
    if len(j):
        ok = np.where(j.index.get_level_values("market") == "spreads", np.isclose(j.point, -j.point_b),
                      np.where(j.index.get_level_values("market") == "totals", np.isclose(j.point, j.point_b), True))
        j = j[ok]
    j["p_a"] = no_vig_two_way(j.dec.values, j.dec_b.values, devig) if len(j) else []
    return j.reset_index()


def reference_mu(pairs: pd.DataFrame, sigma: dict) -> pd.DataFrame:
    """Per book pair: the implied outcome mean mu (spreads: home margin, totals: total). Moneyline keeps p_a."""
    pairs = pairs.copy()
    pairs["mu"] = np.nan
    for m, side in (("spreads", "home"), ("totals", "over")):
        i = pairs.market == m
        if i.any():
            pairs.loc[i, "mu"] = solve_mu(pairs.loc[i, "p_a"].values, pairs.loc[i, "point"].values, sigma[m], m, side)
    return pairs


def candidates(q: pd.DataFrame, sigma: dict, fair_source: str = "pinnacle", devig: str = "multiplicative") -> pd.DataFrame:
    """Every scope-book quote with its fair win/push probability and EV per unit staked.
    fair_source: 'pinnacle' (fallback to leave-one-out scope consensus) or 'consensus' (never Pinnacle)."""
    pairs = reference_mu(two_way(q, devig), sigma)
    pin = pairs[pairs.book == "pinnacle"].set_index(["window", "game_id", "market"])[["p_a", "mu"]]
    scope = pairs[pairs.book != "pinnacle"]
    c = q[q.is_scope].copy()
    k = ["window", "game_id", "market"]
    # leave-one-out consensus: median over the other scope books of this game/market/window
    cons = scope[k + ["book", "p_a", "mu"]]
    loo = c[k + ["book"]].drop_duplicates().merge(cons, on=k, suffixes=("", "_ref"))
    loo = loo[loo.book != loo.book_ref].groupby(k + ["book"])[["p_a", "mu"]].median().rename(
        columns={"p_a": "p_a_cons", "mu": "mu_cons"})
    c = c.join(loo, on=k + ["book"])
    if fair_source == "pinnacle":
        c = c.join(pin.rename(columns={"p_a": "p_a_pin", "mu": "mu_pin"}), on=k)
        c["ref"] = np.where(c.p_a_pin.notna(), "pinnacle", np.where(c.p_a_cons.notna(), "consensus", None))
        c["p_a_ref"] = c.p_a_pin.fillna(c.p_a_cons)
        c["mu_ref"] = c.mu_pin.fillna(c.mu_cons)
    else:
        c["ref"] = np.where(c.p_a_cons.notna(), "consensus", None)
        c["p_a_ref"], c["mu_ref"] = c.p_a_cons, c.mu_cons
    c = c[c.ref.notna()].copy()
    c["p_win"], c["p_push"] = np.nan, 0.0
    i = c.market == "h2h"
    c.loc[i, "p_win"] = np.where(c.loc[i, "side"] == "home", c.loc[i, "p_a_ref"], 1 - c.loc[i, "p_a_ref"])
    for m, sides in (("spreads", ("home", "away")), ("totals", ("over", "under"))):
        for s in sides:
            j = (c.market == m) & (c.side == s) & c.mu_ref.notna()
            if j.any():
                w, pu = win_push(c.loc[j, "mu_ref"].values, c.loc[j, "point"].values, sigma[m], m, s)
                c.loc[j, "p_win"], c.loc[j, "p_push"] = w, pu
    c = c[c.p_win.notna()]
    c["p_loss"] = 1 - c.p_win - c.p_push
    c["ev"] = c.p_win * (c.dec - 1) - c.p_loss
    return c


def best_bets(c: pd.DataFrame) -> pd.DataFrame:
    """Best price at pick time = the scope-book quote with the highest EV; one bet per window x game x market."""
    c = c.sort_values("ev", ascending=False)
    return c.drop_duplicates(["window", "game_id", "market"]).reset_index(drop=True)


def estimate_sigma(q: pd.DataFrame, seasons=DISCOVERY, window="T15") -> dict:
    """Residual SD of the result around Pinnacle's implied mean line, discovery seasons only."""
    d = q[(q.book == "pinnacle") & q.season.isin(seasons) & (q.window == window) & (q.game_status == 3)]
    out = {}
    sp = d[(d.market == "spreads") & (d.side == "home")]
    out["spreads"] = float(np.std((sp.home_score - sp.away_score) - (-sp.point), ddof=1)) if len(sp) > 30 else 12.5
    to = d[(d.market == "totals") & (d.side == "over")]
    out["totals"] = float(np.std((to.home_score + to.away_score) - to.point, ddof=1)) if len(to) > 30 else 18.5
    return out
