"""Monte Carlo bankroll simulation from the graded record.

Whole slate-days are resampled (block bootstrap), so bets on the same night stay together and their correlation is kept.
An optional 'haircut' lowers every winning payout, to show what slightly worse prices would do.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import record


def run(markets: list[str], days: int = 120, sims: int = 5000, bankroll: float = 100.0, stake: float = 1.0,
        staking: str = "flat", haircut: float = 0.0, seasons: list[str] | None = None, seed: int = 7, progress=None) -> dict:
    d = record.all_bets(include_live=True)
    d = d[d.market.isin(markets)]
    if seasons:
        d = d[d.season.isin(seasons)]
    if d.empty:
        raise ValueError("No bets for the selected markets")
    dec = d.dec.values.astype(float)
    res = d.result.values.astype(float)
    ret = np.where(res > 0, dec * (1 - haircut) - 1, np.where(res < 0, -1.0, 0.0))        # profit per 1 unit staked
    slates, idx = np.unique(d.slate.values, return_inverse=True)
    order = np.argsort(idx, kind="stable")
    starts = np.searchsorted(idx[order], np.arange(len(slates)))
    counts = np.bincount(idx, minlength=len(slates))
    rets_sorted = ret[order]
    rng = np.random.default_rng(seed)
    sims = int(min(max(sims, 200), 20000))
    days = int(min(max(days, 10), 400))
    paths = np.empty((sims, days + 1))
    paths[:, 0] = bankroll
    pick = rng.integers(0, len(slates), (sims, days))
    for t in range(days):
        if progress and t % 20 == 0:
            progress(t / days, f"Simulating day {t} of {days}")
        k = pick[:, t]
        if staking == "flat":
            day_ret = _day_sum(rets_sorted, starts, counts, k)
            paths[:, t + 1] = paths[:, t] + stake * day_ret
        else:   # fixed fraction of the current bankroll per bet (stake = percent)
            day_ret = _day_sum(rets_sorted, starts, counts, k)
            paths[:, t + 1] = np.maximum(paths[:, t] * (1 + stake / 100 * day_ret), 0)
    final = paths[:, -1]
    peak = np.maximum.accumulate(paths, axis=1)
    dd = (peak - paths).max(1)
    q = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    step = max(1, days // 120)
    hist, edges = np.histogram(final - bankroll, bins=40)
    per_day = counts.mean()
    return dict(
        markets=markets, days=days, sims=sims, bankroll=bankroll, stake=stake, staking=staking, haircut=haircut,
        bets_per_day=round(float(per_day), 2), pool_days=len(slates), pool_bets=len(d),
        bands=dict(day=list(range(0, days + 1, step)), **{k: [round(float(x), 2) for x in q[i][::step]] for i, k in enumerate(["p5", "p25", "p50", "p75", "p95"])}),
        sample_paths=[[round(float(x), 2) for x in paths[i][::step]] for i in range(min(24, sims))],
        final=dict(median=float(np.median(final)), mean=float(final.mean()), p5=float(np.percentile(final, 5)), p95=float(np.percentile(final, 95))),
        prob_profit=float((final > bankroll).mean()), prob_loss_20=float((final < bankroll * .8).mean()),
        ruin=float((paths.min(1) <= 0).mean()), drawdown_median=float(np.median(dd)), drawdown_p95=float(np.percentile(dd, 95)),
        hist=dict(counts=hist.tolist(), edges=[round(float(e), 2) for e in edges]),
        roi_median=float(np.median((final - bankroll) / max(stake * per_day * days, 1e-9))) if staking == "flat" else None)


def _day_sum(rets_sorted, starts, counts, k):
    c = np.cumsum(np.r_[0.0, rets_sorted])
    return c[starts[k] + counts[k]] - c[starts[k]]
