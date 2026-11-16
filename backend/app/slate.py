"""Today's board: the games of an ET day, each market's decision window, and the picks logged for it."""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import DATA_DIR
from .markets import MARKETS, RULE_TO_MARKET
from . import record

ET = "America/New_York"
WINDOW_FOR = {"NOON": ["h2h"], "T30G": ["totals"], "T30P": ["player_rebounds", "player_rebounds_assists"],
              "T60P": ["player_threes", "player_blocks"]}


def _sched_stamp() -> float:
    f = DATA_DIR / "results" / "schedule_2026-27.parquet"
    return f.stat().st_mtime if f.exists() else 0


@lru_cache(maxsize=2)
def _schedule(stamp: float) -> pd.DataFrame:
    import livepicks
    return livepicks.schedule()


def schedule() -> pd.DataFrame:
    return _schedule(_sched_stamp())


def today_et() -> str:
    return pd.Timestamp.now(tz=ET).strftime("%Y-%m-%d")


def _read_jsonl(fp) -> pd.DataFrame:
    if not fp.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(x) for x in open(fp, encoding="utf-8") if x.strip()])


def picks_for(day: str) -> pd.DataFrame:
    """Logged picks for a day: graded where available, else as logged; the replay covers slates before the app's log."""
    lv = record.live()
    d = lv[lv.slate == day] if len(lv) else lv
    if not len(d):
        raw = _read_jsonl(DATA_DIR / "live" / "picks.jsonl")
        if len(raw):
            d = raw[raw.slate == day].assign(state="pending", result=np.nan, profit=np.nan, source="live")
            d["market"] = d.market.where(d.market.isin(MARKETS), d.rule.map(RULE_TO_MARKET))
    return d


def board(day: str | None = None) -> dict:
    day = day or today_et()
    s = schedule()
    g = s[s.slate_date_et == day].sort_values("tip_utc")
    now = pd.Timestamp.now(tz="UTC")
    ticks = _read_jsonl(DATA_DIR / "live" / "ticks.jsonl")
    tick_status = {} if ticks.empty else dict(zip(ticks.key, ticks.status))
    picks = picks_for(day)
    games = []
    for r in g.itertuples():
        tip = pd.Timestamp(r.tip_utc)
        windows = []
        for key, mins, w in ((f"T60P|{r.gameId}", 60, "T60P"), (f"T30P|{r.gameId}", 30, "T30P"),
                             (f"T30G|{tip.strftime('%Y-%m-%dT%H:%M:%SZ')}", 30, "T30G")):
            at = tip - pd.Timedelta(minutes=mins)
            st = tick_status.get(key) or ("open" if at <= now < at + pd.Timedelta(minutes=10) and now < tip else
                                          "upcoming" if now < at else "closed")
            windows.append(dict(key=key, window=w, at=at.isoformat(), status=st, markets=WINDOW_FOR[w]))
        gp = picks[(picks.game_id.astype(str).str.lstrip("0") == str(r.gameId).lstrip("0"))] if len(picks) and "game_id" in picks else picks.iloc[0:0]
        games.append(dict(game_id=r.gameId, tip=tip.isoformat(), status=int(r.gameStatus), status_text=r.gameStatusText,
                          home=dict(code=r.homeTeam_teamTricode, city=r.homeTeam_teamCity, name=r.homeTeam_teamName,
                                    score=None if pd.isna(r.homeTeam_score) else int(r.homeTeam_score)),
                          away=dict(code=r.awayTeam_teamTricode, city=r.awayTeam_teamCity, name=r.awayTeam_teamName,
                                    score=None if pd.isna(r.awayTeam_score) else int(r.awayTeam_score)),
                          windows=windows, picks=len(gp)))
    noon = pd.Timestamp(f"{day} 12:00", tz=ET).tz_convert("UTC")
    noon_key = f"NOON|{day}"
    noon_st = tick_status.get(noon_key) or ("upcoming" if now < noon else "open" if now < noon + pd.Timedelta(minutes=10) else "closed")
    return dict(day=day, now=now.isoformat(), games=games, noon=dict(key=noon_key, window="NOON", at=noon.isoformat(), status=noon_st, markets=["h2h"]),
                picks=enrich(picks), days=nearby_days(day))


def nearby_days(day: str) -> list[str]:
    s = schedule()
    days = sorted(s.slate_date_et.unique())
    if day not in days:
        days = sorted(days + [day])
    i = days.index(day)
    return days[max(0, i - 7): i + 8]


def _teams() -> dict:
    s = schedule()
    return {r.gameId.lstrip("0"): (r.awayTeam_teamTricode, r.homeTeam_teamTricode) for r in s.itertuples()}


def enrich(p: pd.DataFrame) -> list[dict]:
    if not len(p):
        return []
    teams = _teams()
    out = []
    for r in p.to_dict("records"):
        m = r.get("market")
        meta = MARKETS.get(m, {})
        dec = float(r["dec"])
        a_h = teams.get(str(r.get("game_id", "")).lstrip("0"), ("", ""))
        rec = dict(market=m, label=meta.get("label"), short=meta.get("short"), kind=meta.get("kind"), window=meta.get("window"),
                   slate=r.get("slate"), game_id=str(r.get("game_id")), away=a_h[0], home=a_h[1], who=r.get("who"),
                   side=r.get("side"), point=_num(r.get("point")), book=r.get("book"), price=int(r["price"]), dec=dec,
                   ev=float(r["ev"]), p_win=_num(r.get("p_win")), breakeven=1 / dec, p_market=_num(r.get("p_market")),
                   p_player=_num(r.get("p_player")), ref=r.get("ref"), decision_utc=r.get("decision_utc"), tip_utc=r.get("tip_utc"),
                   state=r.get("state") or "pending", result=_num(r.get("result")), profit=_num(r.get("profit")), source=r.get("source"))
        rec["confidence"] = _grade(rec["ev"], m)
        out.append(rec)
    return sorted(out, key=lambda x: (x["tip_utc"] or "", -x["ev"]))


def _num(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _grade(ev: float, market: str) -> str:
    """Edge above the market's frozen floor: props clear a 7.5-10% floor, game markets 0%, so their bands differ."""
    floor = {"player_rebounds": .10, "player_threes": .10, "player_rebounds_assists": .075, "player_blocks": .075}.get(market)
    over = ev - (floor or 0.0)
    a, b = (.08, .03) if floor is not None else (.03, .012)
    return "A" if over >= a else "B" if over >= b else "C"


def player_form(name: str, stat: str, n: int = 12, before: str | None = None) -> dict:
    """The player's games before the pick's slate (what was known at pick time), from the box scores on disk."""
    import livepicks
    logs = livepicks.load_logs(["2025-26", "2026-27"])
    d = logs[logs.PLAYER_NAME == name].assign(_d=pd.to_datetime(logs.GAME_DATE))
    if before:
        d = d[d._d < pd.Timestamp(before)]
    d = d.sort_values("_d").tail(n)
    if stat == "RA":
        vals = (d.REB + d.AST).tolist()
    else:
        vals = d[stat].tolist() if stat in d else []
    return dict(player=name, stat=stat, games=[dict(date=str(x.GAME_DATE)[:10], matchup=x.MATCHUP, value=float(v), minutes=float(x.MIN or 0))
                                              for x, v in zip(d.itertuples(), vals)])
