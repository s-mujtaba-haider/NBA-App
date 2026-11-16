"""Track record of the six markets: graded bets of 2024-25 and 2025-26 (the evidence the rule was judged on) plus the
2026-27 live season (pick-time replay of the same code, then the picks this app logs itself).

All figures are flat 1 unit per bet at the best price across the 8 scope books at pick time.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import norm

from .config import DATA_DIR, LEDGER_DIR
from .markets import MARKETS, ORDER, RULE_TO_MARKET

SEED = 20261025
_lock = threading.Lock()
_live_cache: dict = {}


def american(dec: np.ndarray) -> np.ndarray:
    dec = np.asarray(dec, float)
    return np.where(dec >= 2, np.round((dec - 1) * 100), np.round(-100 / (dec - 1))).astype(int)


@lru_cache(maxsize=1)
def backtest() -> pd.DataFrame:
    d = pd.read_parquet(LEDGER_DIR / "bets.parquet")
    d = d.rename(columns={"player": "who"})
    d["who"] = d.who.fillna("GAME")
    d["p_win"] = (d.ev + 1) / d.dec
    d["source"] = "backtest"
    d["game_id"] = None
    return d


def _live_frames() -> list[pd.DataFrame]:
    frames = []
    rp = LEDGER_DIR / "replay_2026-27.csv"
    if rp.exists():
        r = pd.read_csv(rp, dtype={"game_id": str})
        r["source"] = "replay"
        frames.append(r)
    own = DATA_DIR / "live" / "picks_graded.csv"
    if own.exists():
        o = pd.read_csv(own, dtype={"game_id": str})
        o["source"] = "live"
        frames.append(o)
    return frames


def live() -> pd.DataFrame:
    """2026-27 picks, graded where the result is in. Replay rows cover slates before the app's own log starts."""
    own = DATA_DIR / "live" / "picks_graded.csv"
    stamp = own.stat().st_mtime if own.exists() else 0
    with _lock:
        if _live_cache.get("stamp") == stamp:
            return _live_cache["df"]
        frames = _live_frames()
        if not frames:
            d = pd.DataFrame(columns=["market", "slate", "who", "side", "point", "book", "dec", "ev", "p_win", "result", "profit", "state", "source"])
        else:
            d = pd.concat(frames, ignore_index=True)
            d["market"] = d.market.where(d.market.isin(ORDER), d.rule.map(RULE_TO_MARKET))
            d = d[d.market.isin(ORDER)]
            if (d.source == "live").any():
                first_own = d[d.source == "live"].slate.min()
                d = d[(d.source == "live") | (d.slate < first_own)]
        d["season"] = "2026-27"
        d["slate"] = d.slate.astype(str)
        _live_cache.update(stamp=stamp, df=d)
        return d


def graded_live() -> pd.DataFrame:
    d = live()
    return d[(d.get("state", "graded") == "graded") & d.profit.notna()] if len(d) else d


def all_bets(include_live: bool = True) -> pd.DataFrame:
    cols = ["market", "season", "slate", "book", "who", "side", "point", "dec", "ev", "p_win", "result", "profit", "source"]
    parts = [backtest()[cols]]
    if include_live:
        g = graded_live()
        if len(g):
            parts.append(g[cols])
    d = pd.concat(parts, ignore_index=True)
    d["price"] = american(d.dec)
    return d


# ---------------------------------------------------------------- statistics
def ci_low(d: pd.DataFrame, seed: int = SEED, draws: int = 2000) -> float:
    """Official check: the lower of the normal 95% bound and the slate-day bootstrap bound."""
    p = d.profit.values.astype(float)
    if len(p) < 2:
        return float("nan")
    normal = p.mean() - norm.ppf(.975) * p.std(ddof=1) / np.sqrt(len(p))
    u, g = np.unique(d.slate.values, return_inverse=True)
    P, N = np.bincount(g, weights=p), np.bincount(g).astype(float)
    i = np.random.default_rng(seed).integers(0, len(u), (draws, len(u)))
    return float(min(normal, np.quantile(P[i].sum(1) / N[i].sum(1), .025)))


def _stats(d: pd.DataFrame) -> dict:
    if not len(d):
        return dict(bets=0, won=0, lost=0, push=0, units=0.0, roi=None, hit_rate=None, avg_price=None, avg_ev=None)
    won, lost = int((d.result > 0).sum()), int((d.result < 0).sum())
    return dict(bets=len(d), won=won, lost=lost, push=int((d.result == 0).sum()), units=round(float(d.profit.sum()), 2),
                roi=float(d.profit.mean()), hit_rate=won / max(won + lost, 1), avg_price=int(american([np.median(d.dec)])[0]),
                avg_ev=float(d.ev.mean()))


@lru_cache(maxsize=1)
def _summary_backtest() -> dict:
    b = backtest()
    out = {}
    for m in ORDER:
        d = b[b.market == m]
        s25 = d[d.season == "2025-26"]
        weekly = d.assign(w=pd.to_datetime(d.slate).dt.to_period("W").astype(str)).groupby("w").profit.sum().cumsum()
        out[m] = dict(two_season=dict(**_stats(d), ci_low=ci_low(d)), season_2025_26=_stats(s25),
                      season_2024_25=_stats(d[d.season == "2024-25"]), spark=[round(float(x), 2) for x in weekly.values])
    return out


def summary() -> dict:
    lv = graded_live()
    markets = []
    for m in ORDER:
        meta = MARKETS[m]
        bt = _summary_backtest()[m]
        two = bt["two_season"]
        status = "WINNER" if two["roi"] >= .03 and two["ci_low"] > 0 and bt["season_2025_26"]["roi"] >= .03 else "SHOWN"
        markets.append(dict(key=m, **meta, status=status, **bt, live=_stats(lv[lv.market == m]) if len(lv) else _stats(lv)))
    b = backtest()
    s25 = b[b.season == "2025-26"]
    months = s25.assign(mo=s25.slate.str[:7]).groupby("mo").profit.sum()
    by_day = s25.sort_values("slate").groupby("slate").profit.sum().cumsum()
    totals = dict(two_season=_stats(b), season_2025_26=dict(**_stats(s25), months_profit=int((months > 0).sum()), months=len(months),
                                                            worst_drop=round(float((by_day.cummax() - by_day).max()), 2),
                                                            bets_per_day=round(len(s25) / s25.slate.nunique(), 1)),
                  live=_stats(lv), live_last_slate=str(lv.slate.max()) if len(lv) else None)
    return dict(markets=markets, totals=totals, winners=sum(x["status"] == "WINNER" for x in markets))


def equity(markets: list[str] | None = None, include_live: bool = True) -> dict:
    d = all_bets(include_live)
    if markets:
        d = d[d.market.isin(markets)]
    day = d.groupby(["slate", "market"]).profit.sum().unstack(fill_value=0).sort_index()
    cum = day.cumsum()
    total = day.sum(axis=1).cumsum()
    season = d.groupby("slate").season.first().reindex(day.index)
    return dict(dates=list(day.index), total=[round(float(x), 2) for x in total.values], season=list(season.values),
                series={m: [round(float(x), 2) for x in cum[m].values] for m in cum.columns})


def monthly(include_live: bool = True) -> dict:
    d = all_bets(include_live)
    d["month"] = d.slate.str[:7]
    t = d.groupby(["month", "market"]).profit.agg(["sum", "size"]).reset_index()
    return dict(rows=[dict(month=r.month, market=r.market, units=round(float(r["sum"]), 2), bets=int(r["size"])) for _, r in t.iterrows()])


def by_book(include_live: bool = True) -> list[dict]:
    d = all_bets(include_live)
    return [dict(book=k, **_stats(g)) for k, g in d.groupby("book")]


def edge_buckets(market: str | None = None) -> list[dict]:
    """Realised ROI by the model's expected value at pick time: does a bigger edge pay more?"""
    d = backtest()
    if market:
        d = d[d.market == market]
    bins = [-1, .05, .1, .15, .2, .3, 10]
    labels = ["0-5%", "5-10%", "10-15%", "15-20%", "20-30%", "30%+"]
    d = d.assign(b=pd.cut(d.ev, bins, labels=labels))
    return [dict(bucket=str(k), bets=len(g), roi=float(g.profit.mean()) if len(g) else None, expected=float(g.ev.mean()) if len(g) else None)
            for k, g in d.groupby("b", observed=False)]


def calibration(market: str | None = None) -> list[dict]:
    d = backtest()
    if market:
        d = d[d.market == market]
    d = d[d.result != 0]
    d = d.assign(b=pd.cut(d.p_win, np.linspace(0, 1, 21)))
    out = []
    for k, g in d.groupby("b", observed=True):
        if len(g) >= 15:
            out.append(dict(p=float(g.p_win.mean()), actual=float((g.result > 0).mean()), n=len(g)))
    return out


def bets(market: str | None = None, season: str | None = None, q: str | None = None, result: str | None = None,
         limit: int = 100, offset: int = 0) -> dict:
    d = all_bets(True)
    if market:
        d = d[d.market == market]
    if season:
        d = d[d.season == season]
    if q:
        d = d[d.who.str.contains(q, case=False, na=False) | d.book.str.contains(q, case=False, na=False)]
    if result in ("won", "lost", "push"):
        d = d[{"won": d.result > 0, "lost": d.result < 0, "push": d.result == 0}[result]]
    d = d.sort_values(["slate", "market"], ascending=[False, True])
    page = d.iloc[offset:offset + limit]
    return dict(total=len(d), rows=_records(page))


def _records(d: pd.DataFrame) -> list[dict]:
    out = []
    for r in d.to_dict("records"):
        out.append({k: (None if isinstance(v, float) and not np.isfinite(v) else (v.item() if hasattr(v, "item") else v)) for k, v in r.items()})
    return out
