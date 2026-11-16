"""Runs the live pick engine (engine/livepicks.py) as background jobs.

* picks   one pass over the decision windows that are due now (billable: about 1-2 Odds API credits per window)
* results refresh schedule and box scores from stats.nba.com, then grade the logged picks (free)
* plan    the day's decisions and credit estimate (free, no calls)
Every Odds API call goes through engine/nba/oddsapi_gate.py: approval record, request and credit caps, ledger.
"""
from __future__ import annotations

import io
import json
import logging
import threading
from contextlib import redirect_stdout

import pandas as pd

from . import jobs
from .config import DATA_DIR, settings

logger = logging.getLogger("engine")
_run_lock = threading.Lock()


def _capture(fn, *a, **k):
    buf = io.StringIO()
    with redirect_stdout(buf):
        out = fn(*a, **k)
    for line in buf.getvalue().splitlines():
        if line.strip():
            logger.info(line.strip()[:300])
    return out


def ensure_registered() -> None:
    import livepicks
    _capture(livepicks.register)


def credit_status() -> dict:
    import livepicks
    from nba import oddsapi_gate as gate
    a = gate._load_approvals()
    op = next((o for o in a.get("operations", []) if o["id"] == livepicks.OP), None)
    out = dict(configured=settings.odds_configured, operation=livepicks.OP, registered=op is not None)
    if op:
        out.update(status=op.get("status"), credits_spent=op.get("credits_spent", 0), max_credits=op.get("max_credits"),
                   requests_done=op.get("requests_done", 0), max_requests=op.get("max_requests"))
    out["proxy"] = dict(gate.lock_state) if getattr(gate, "lock_state", None) else None
    return out


def plan(day: str | None = None) -> dict:
    import livepicks
    day = day or pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    d = livepicks.decisions(livepicks.schedule(), day)
    cost = sum({"NOON": 1, "T30G": 1, "T30P": 2, "T60P": 2}[x[1]] for x in d)
    return dict(day=day, decisions=[dict(key=k, window=w, at=n.isoformat()) for k, w, n, _, _ in d], credits=cost)


def job_picks(ctx) -> dict:
    import livepicks
    if not settings.odds_configured:
        raise RuntimeError("Odds feed not configured: set ODDS_API_BASE and ODDS_PROXY_TOKEN in .env")
    with _run_lock:
        ensure_registered()
        ctx.progress(.1, "Checking due decision windows", force=True)
        before = _count(DATA_DIR / "live" / "picks.jsonl")
        ran = _capture(livepicks.tick)
        new = _count(DATA_DIR / "live" / "picks.jsonl") - before
    msg = f"{ran} window(s) run, {new} new pick(s)" if ran else "No decision window is open right now"
    logger.info(msg)
    return dict(message=msg, windows=ran, picks=new)


def job_now_test(ctx) -> dict:
    import livepicks
    if not settings.odds_configured:
        raise RuntimeError("Odds feed not configured: set ODDS_API_BASE and ODDS_PROXY_TOKEN in .env")
    with _run_lock:
        ensure_registered()
        ctx.progress(.1, "Test run on current odds (stored apart, never counted)", force=True)
        d = _capture(livepicks.now_test)
    return dict(message=f"Test run: {len(d)} pick(s) on current odds", picks=len(d))


def job_results(ctx) -> dict:
    import livepicks
    with _run_lock:
        ctx.progress(.05, "Refreshing schedule and box scores (stats.nba.com)", force=True)
        _capture(livepicks.refresh_results)
        ctx.progress(.8, "Grading logged picks", force=True)
        t = _capture(livepicks.settle, refresh=False)
    n = 0 if t is None else int((t.state == "graded").sum())
    msg = f"Results refreshed; {n} logged pick(s) graded" if t is not None else "Results refreshed; no live picks logged yet"
    return dict(message=msg, graded=n)


def submit(kind: str) -> str:
    fn = {"picks": job_picks, "results": job_results, "test": job_now_test}[kind]
    return jobs.submit(kind, fn, league="NBA", params={})


def _count(fp) -> int:
    if not fp.exists():
        return 0
    with open(fp, encoding="utf-8") as f:
        return sum(1 for x in f if x.strip())


def scheduler(stop: threading.Event) -> None:
    """AUTO_PICKS: a pass every 30 s while any window of today is pending. AUTO_RESULTS: a free refresh every few hours."""
    import livepicks
    last_results = None
    while not stop.wait(30):
        try:
            if settings.auto_picks and settings.odds_configured:
                day = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
                if livepicks.pending(day) and not _run_lock.locked():
                    with _run_lock:
                        ensure_registered()
                        _capture(livepicks.tick, day=day)
            now = pd.Timestamp.now(tz="UTC")
            if settings.auto_results and (last_results is None or now - last_results > pd.Timedelta(hours=settings.results_every_hours)):
                last_results = now
                submit("results")
        except Exception as e:                                          # noqa: BLE001
            logger.warning("scheduler pass failed: %s", e)


def ticks(limit: int = 50) -> list[dict]:
    fp = DATA_DIR / "live" / "ticks.jsonl"
    if not fp.exists():
        return []
    rows = [json.loads(x) for x in open(fp, encoding="utf-8") if x.strip()]
    return rows[-limit:][::-1]
