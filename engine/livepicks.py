"""Live picks for the six WINNER markets, made BEFORE tip from current odds with the frozen rules, unchanged.

    python engine/livepicks.py register     write the capped credit record (once; cap from LIVE_CREDIT_CAP)
    python engine/livepicks.py plan [DAY]   the day's decision times and the credit estimate (no calls)
    python engine/livepicks.py tick         one pass: fetch and pick whatever is due now (billable, about 1-2 credits a call)
    python engine/livepicks.py loop         tick every 30 s until every window of today has passed
    python engine/livepicks.py now          test run on current odds, outside the windows; stored apart, never counted
    python engine/livepicks.py results      refresh schedule and box scores from stats.nba.com (free)
    python engine/livepicks.py settle       refresh results, grade logged picks -> data/live/picks_graded.csv

Market       Window    Fair price and selection (frozen rule files in data/rules/)
moneyline    12:00 ET  Pinnacle no-vig (power), EV >= 0                      frozen_rules_game.json
game totals  T-30      Pinnacle no-vig (multiplicative) on a fitted total    frozen_rules_game.json
rebounds     T-30      market + player model stack, EV >= 0.10               frozen_rules_props_T30.json
reb + ast    T-30      market + player model stack, EV >= 0.075              frozen_rules_new_markets.json
threes       T-60      market + player model stack, EV >= 0.10               frozen_rules_props_stack.json
blocks       T-60      market + player model stack, EV >= 0.075              frozen_rules_props_stack.json

No look-ahead: a quote counts only if stamped at or before the decision, player numbers use earlier dates only, and these
functions never read a result. A window is fetched only inside [decision, decision + LATE_MIN] and before tip; a missed one
is logged as missed, never fetched late. picks.jsonl and ticks.jsonl are append-only. All Odds API calls go through the gate.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

import os

ENGINE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("BASELINE_HOME") or ENGINE.parent)
sys.path.insert(0, str(ENGINE))
from nba import game_markets as gm  # noqa: E402
from nba import oddsapi_gate as gate  # noqa: E402
from nba import pricing, projection, props  # noqa: E402
from nba.scope_gate import SCOPE_KEYS, american_to_decimal, settle as settle_profit  # noqa: E402

RULES = ENGINE.parent / "data" / "rules"                 # frozen, shipped with the app (read only)
LIVE = ROOT / "data" / "live"
PICKS, TICKS = LIVE / "picks.jsonl", LIVE / "ticks.jsonl"
COEF = RULES / "frozen_stack_coefficients.json"
SEASONS = ["2023-24", "2024-25", "2025-26", "2026-27"]
SEASON = "2026-27"
OP = os.environ.get("ODDS_OPERATION_ID", "BASELINE_LIVE")
ODDS, EVENT_ODDS, EVENTS = "/v4/sports/basketball_nba/odds", "/v4/sports/basketball_nba/events/{}/odds", "/v4/sports/basketball_nba/events"
BASE = dict(bookmakers=gm.BOOKS, oddsFormat="american", dateFormat="iso")
LATE_MIN = 10
EPS = 1e-4
RULE_NAMES = {"h2h": "moneyline NOON", "totals": "totals T-30", "player_rebounds": "rebounds T-30", "player_rebounds_assists": "rebounds+assists T-30",
              "player_threes": "threes T-60", "player_blocks": "blocks T-60"}
WINDOW_MARKETS = {"NOON": ["h2h"], "T30": ["totals", "player_rebounds", "player_rebounds_assists"], "T60": ["player_threes", "player_blocks"]}
PROP_MARKETS = {"player_rebounds": "REB", "player_threes": "FG3M", "player_blocks": "BLK", "player_rebounds_assists": None}
THIN_FILTER = {"player_rebounds", "player_rebounds_assists"}     # T-30 pipelines drop thin consensus prices; the T-60 pipeline does not


def iso(t):
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- frozen rules
def load_rules() -> dict:
    out = RULES
    gr = json.loads((out / "frozen_rules_game.json").read_text())
    t30 = json.loads((out / "frozen_rules_props_T30.json").read_text())["rules"]
    st = json.loads((out / "frozen_rules_props_stack.json").read_text())["rules"]
    new = json.loads((out / "frozen_rules_new_markets.json").read_text())["rules"]
    pick = lambda rules, m: next(r for r in rules if r["market"] == m)   # noqa: E731
    return dict(sigma=gr["sigma"],
                h2h=next(r for r in gr["rules"] if r["market"] == "h2h" and r["window"] == "NOON"),
                totals=next(r for r in gr["rules"] if r["market"] == "totals" and r["window"] == "T30"),
                player_rebounds=pick(t30, "player_rebounds"), player_threes=pick(st, "player_threes"),
                player_blocks=pick(st, "player_blocks"), player_rebounds_assists=pick(new, "player_rebounds_assists"))


def load_logs(seasons=SEASONS) -> pd.DataFrame:
    fps = [ROOT / f"data/results/player_logs_{s}.parquet" for s in seasons]
    return pd.concat([pd.read_parquet(f) for f in fps if f.exists()], ignore_index=True)


# ---------------------------------------------------------------- pick logic (pure: no network, no results)
def parse_props(ev: dict, decision, markets) -> pd.DataFrame:
    """Over/under player quotes stamped at or before the decision."""
    rows = []
    for bk in (ev or {}).get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] not in markets or pd.Timestamp(mk["last_update"]) > decision:
                continue
            for o in mk["outcomes"]:
                side = str(o.get("name", "")).lower()
                if side in ("over", "under") and o.get("point") is not None and o.get("description"):
                    rows.append((ev.get("id"), bk["key"], mk["key"], o["description"], side, float(o["point"]), o["price"], mk["last_update"]))
    q = pd.DataFrame(rows, columns=["event_id", "book", "market", "player", "side", "point", "price", "last_update"])
    q = q.drop_duplicates(["book", "market", "player", "side", "point"])
    q["dec"] = american_to_decimal(q.price) if len(q) else []
    q["is_scope"] = q.book.isin(SCOPE_KEYS)
    return q


class Names:
    """Quoted name -> box-score name, from what is known before tip: the two teams' players over two seasons, then anyone this
    season, then anyone earlier. An unknown name (a true debut) stays in play with no model input: market price only."""

    def __init__(self, logs: pd.DataFrame, slate: str):
        b = logs[pd.to_datetime(logs.GAME_DATE) < pd.Timestamp(slate)]
        cur = b[b.season == b.season.max()] if len(b) else b
        recent = b[b.season.isin(sorted(b.season.unique())[-2:])] if len(b) else b   # opening nights: a team may have no logs this season yet
        self.by_team = recent.groupby("TEAM_ABBREVIATION").PLAYER_NAME.apply(lambda s: sorted(set(s))).to_dict()
        self.season = sorted(set(cur.PLAYER_NAME))
        self.ever = sorted(set(b.PLAYER_NAME))

    def match(self, names, teams=()):
        roster = sorted({p for t in teams for p in self.by_team.get(t, [])})
        out = props.match_names(names, roster)
        rest = [n for n in names if out[n] is None]
        for pool in (self.season, self.ever):
            if rest:
                m = {n: {props.norm_name(r): r for r in pool}.get(props.norm_name(n)) for n in rest}
                out.update(m)
                rest = [n for n in rest if out[n] is None]
        return out


def projections_for(logs: pd.DataFrame, slate: str) -> pd.DataFrame:
    """One pre-game row per player: logs strictly before the slate date plus one empty row, through the backtest's builder."""
    b = logs[pd.to_datetime(logs.GAME_DATE) < pd.Timestamp(slate)]
    last = b.assign(_d=pd.to_datetime(b.GAME_DATE)).sort_values("_d").drop_duplicates("PLAYER_ID", keep="last")
    syn = last[["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "season"]].assign(GAME_ID="LIVE", GAME_DATE=slate)
    p = projection.build_projections(pd.concat([b, syn], ignore_index=True))
    return p[p.GAME_ID == "LIVE"].drop_duplicates("PLAYER_NAME", keep="last").set_index("PLAYER_NAME")


def _logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def prop_picks(q: pd.DataFrame, market: str, rule: dict, proj: pd.DataFrame, fz: dict) -> pd.DataFrame:
    """Highest-EV scope quote per event x player under the frozen stack; only picks with EV at or above the frozen floor."""
    c = props.fair_and_ev(q[q.market == market].assign(window="LIVE"), rule["devig"])
    if c.empty:
        return c
    if market in THIN_FILTER:
        c = c[~((c.ref == "consensus") & (c.n_cons.fillna(0) < 2))]
        if c.empty:
            return c
    if market == "player_rebounds_assists":
        mean = (c.box_name.map(proj.proj_REB) + c.box_name.map(proj.proj_AST)).values.astype(float)
        r = fz["combo_size"][market]
        mu = np.maximum(np.nan_to_num(mean, nan=1e-6), 1e-6)
        pm = nbinom.sf(np.floor(c.point.values), r, r / (r + mu))
    else:
        stat = PROP_MARKETS[market]
        mean = c.box_name.map(proj[f"proj_{stat}"]).values.astype(float)
        pm = projection.p_over(stat, mean, c.point.values, {k: tuple(v) for k, v in fz["dispersion"].items()})[0]
    c["p_model"] = np.where(np.isfinite(mean) & np.isfinite(pm), pm, c.p_over_ref)
    x1 = _logit(c.p_over_ref)
    b0, b1, b2 = fz["coef"][market]
    c["p_stack"] = 1 / (1 + np.exp(-(b0 + b1 * x1 + b2 * (_logit(c.p_model) - x1))))
    c["p_win"] = np.where(c.side == "over", c.p_stack, 1 - c.p_stack)
    c["p_market"] = np.where(c.side == "over", c.p_over_ref, 1 - c.p_over_ref)       # fair price alone
    c["p_player"] = np.where(c.side == "over", c.p_model, 1 - c.p_model)             # player model alone
    c["ev"] = c.p_win * c.dec - 1
    best = c.sort_values("ev", ascending=False).drop_duplicates(["event_id", "market", "player"])
    return best[best.ev >= rule["tau"]]


def game_picks(events: list, window: str, decision, slate: str, tip_slot, sched: pd.DataFrame, rules: dict, market: str):
    """Moneyline or totals picks; game_markets.event_quotes applies today's-games-only, not-started and quote-time checks."""
    codes = gm.team_codes(sched)
    by_key = {(r.slate_date_et, r.homeTeam_teamTricode, r.awayTeam_teamTricode): r for r in sched.itertuples()}
    stats = dict(events_seen=0, other_day=0, other_tip=0, started=0, unmatched_team=0, quotes_after_decision=0)
    rows = []
    for ev in events or []:
        rows.extend(gm.event_quotes(ev, window, slate, decision, tip_slot, by_key, codes, stats))
    q = gm.finish_quotes(rows) if rows else pd.DataFrame()
    q = q[q.market == market] if len(q) else q
    if q.empty:
        return pd.DataFrame(), stats
    r = rules[market]
    b = pricing.best_bets(pricing.candidates(q, rules["sigma"], r["source"], r.get("devig", "multiplicative")))
    return b[(b.market == market) & (b.ev >= r["tau"])].copy(), stats


def event_for(events, g, codes):
    for e in events or []:
        if codes.get(e["home_team"]) == g.homeTeam_teamTricode and codes.get(e["away_team"]) == g.awayTeam_teamTricode \
                and pd.Timestamp(e["commence_time"]).tz_convert("America/New_York").strftime("%Y-%m-%d") == g.slate_date_et:
            return e
    return None


def game_records(b, slate, nominal, decision, sha):
    return [dict(rule=RULE_NAMES[x.market], slate=slate, game_id=x.game_id, event_id=None, market=x.market, who="GAME", side=x.side,
                 point=None if pd.isna(x.point) else float(x.point), book=x.book, price=int(x.price), dec=float(x.dec), ev=float(x.ev), p_win=float(x.p_win), ref=x.ref,
                 nominal_decision_utc=iso(nominal), decision_utc=iso(decision), tip_utc=iso(x.tip_utc), last_update=x.last_update, raw_sha256=sha)
            for x in b.itertuples()]


def prop_records(b, g, nominal, decision, sha):
    return [dict(rule=RULE_NAMES[x.market], slate=g.slate_date_et, game_id=g.gameId, event_id=x.event_id, market=x.market, who=x.player, side=x.side,
                 point=float(x.point), book=x.book, price=int(x.price), dec=float(x.dec), ev=float(x.ev), p_win=float(x.p_win), ref=x.ref,
                 p_market=float(x.p_market), p_player=float(x.p_player), home=g.homeTeam_teamTricode, away=g.awayTeam_teamTricode,
                 nominal_decision_utc=iso(nominal), decision_utc=iso(decision), tip_utc=iso(g.tip_utc), last_update=x.last_update, raw_sha256=sha)
            for x in b.itertuples()]


# ---------------------------------------------------------------- schedule of decisions
def schedule() -> pd.DataFrame:
    s = gm.load_schedule(SEASONS)
    s["tip_utc"] = pd.to_datetime(s.tip_utc, utc=True)
    s["slate_date_et"] = s.slate_date_et.astype(str)
    return s


def decisions(sched: pd.DataFrame, day: str) -> list:
    """(key, window, nominal decision time, tip slot or None, game or None) for one ET day. One totals call per tip slot, one
    moneyline call per day, one prop call per game and window. Games already final, under way or postponed are left out."""
    g = sched[(sched.slate_date_et == day) & (sched.gameStatus == 1) & (sched.postponedStatus.fillna("") != "Y")]
    if g.empty:
        return []
    out = [(f"NOON|{day}", "NOON", pd.Timestamp(f"{day} 12:00", tz="America/New_York").tz_convert("UTC"), None, None)]
    for tip in sorted(g.tip_utc.unique()):
        tip = pd.Timestamp(tip)
        out.append((f"T30G|{iso(tip)}", "T30G", tip - pd.Timedelta(minutes=30), tip, None))
    for r in g.itertuples():
        out.append((f"T30P|{r.gameId}", "T30P", r.tip_utc - pd.Timedelta(minutes=30), r.tip_utc, r))
        out.append((f"T60P|{r.gameId}", "T60P", r.tip_utc - pd.Timedelta(minutes=60), r.tip_utc, r))
    return sorted(out, key=lambda x: x[2])


def read_jsonl(fp) -> pd.DataFrame:
    if not Path(fp).exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(x) for x in open(fp, encoding="utf-8") if x.strip()])


def append(fp, rec):
    Path(fp).parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def raw_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- one decision
def run_decision(window, tip, g, nominal, sched, rules, fz, logs, picks_fp=PICKS, now_tag=""):
    """Fetch current odds for this decision, pick, append. The decision time is the moment the response arrived."""
    slate = (nominal if tip is None or pd.isna(tip) else tip).tz_convert("America/New_York").strftime("%Y-%m-%d")
    tag = f"opt1_{nominal.strftime('%Y%m%dT%H%M')}{now_tag}"
    if window in ("NOON", "T30G"):
        market = "h2h" if window == "NOON" else "totals"
        data = gate.get(ODDS, OP, _tag=tag, markets=market, **BASE)
        decision = pd.Timestamp.now(tz="UTC")
        b, stats = game_picks(data, "NOON" if window == "NOON" else "T30", decision, slate, tip if window == "T30G" else pd.NaT, sched, rules, market)
        recs = game_records(b, slate, nominal, decision, raw_sha(data)) if len(b) else []
        info = dict(events=stats["events_seen"], started=stats["started"], unmatched=stats["unmatched_team"])
    else:
        day0 = pd.Timestamp(slate, tz="America/New_York")
        evs = gate.get(EVENTS, None, _tag=f"{tag}_events", dateFormat="iso", commenceTimeFrom=iso(day0), commenceTimeTo=iso(day0 + pd.Timedelta(hours=30)))
        ev = event_for(evs, g, gm.team_codes(sched))
        if ev is None:
            return dict(status="no_event", picks=0)
        wm = WINDOW_MARKETS["T30" if window == "T30P" else "T60"]
        props_wanted = [m for m in wm if m in PROP_MARKETS]
        data = gate.get(EVENT_ODDS.format(ev["id"]), OP, _tag=f"{tag}_{g.gameId}", markets=",".join(props_wanted), **BASE)
        decision = pd.Timestamp.now(tz="UTC")
        if pd.Timestamp(ev["commence_time"]) <= decision or g.tip_utc <= decision:
            return dict(status="started", picks=0)
        q = parse_props(data, decision, props_wanted)
        recs = []
        if len(q):
            names = q.player.unique().tolist()
            m = Names(logs, slate).match(names, (g.homeTeam_teamTricode, g.awayTeam_teamTricode))
            q["box_name"] = q.player.map(m)
            proj = projections_for(logs, slate)
            for mk in props_wanted:
                b = prop_picks(q, mk, rules[mk], proj, fz)
                recs += prop_records(b, g, nominal, decision, raw_sha(data)) if len(b) else []
        info = dict(quotes=len(q), books=int(q.book.nunique()) if len(q) else 0)
    for r in recs:
        append(picks_fp, r)
    return dict(status="ok", picks=len(recs), decision=iso(decision), cost=gate.last_headers.get("x-requests-last"), **info)


def tick(now=None, day=None):
    """One pass: anything due now is fetched once; anything past its slot is logged as missed. Safe to run again at any time."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    day = day or now.tz_convert("America/New_York").strftime("%Y-%m-%d")
    sched = schedule()
    t = read_jsonl(TICKS)
    done = set() if t.empty else set(t.key)
    due = [d for d in decisions(sched, day) if d[0] not in done]
    rules, fz, logs = None, None, None
    late = pd.Timedelta(minutes=LATE_MIN)
    ran = 0
    for key, window, nominal, tip, g in due:
        if now < nominal:
            continue
        if now > nominal + late or (tip is not None and now >= tip):
            append(TICKS, dict(key=key, status="missed", nominal=iso(nominal), at=iso(now)))
            continue
        if rules is None:
            rules, fz, logs = load_rules(), json.loads(COEF.read_text()), load_logs()
        try:
            res = run_decision(window, tip, g, nominal, sched, rules, fz, logs)
            append(TICKS, dict(key=key, nominal=iso(nominal), at=iso(now), **res))
            print(key, res, flush=True)
            ran += 1
        except gate.UnbilledFailure as e:                       # not charged: stays due and is tried on the next pass
            print("unbilled failure, retry next pass:", e, flush=True)
    return ran


def pending(day, now=None) -> int:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    t = read_jsonl(TICKS)
    done = set() if t.empty else set(t.key)
    return sum(1 for d in decisions(schedule(), day) if d[0] not in done and now <= d[2] + pd.Timedelta(minutes=LATE_MIN))


def loop(day=None):
    day = day or pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    print("loop for", day, "pending", pending(day), flush=True)
    while pending(day):
        try:
            tick(day=day)
        except gate.ApprovalError as e:                         # cap or halt: stop, a person looks
            print("STOPPED by the credit gate:", e, flush=True)
            raise
        except Exception as e:                                  # noqa: BLE001  a bad pass must not lose the remaining windows
            append(TICKS, dict(key=f"ERROR|{iso(pd.Timestamp.now(tz='UTC'))}", status="error", error=repr(e)[:300]))
            print("pass failed, continuing:", repr(e), flush=True)
        time.sleep(30)
    tick(day=day)                                               # logs anything that ended up missed
    print("all windows of", day, "done", flush=True)


def now_test(day=None):
    """Test on current odds for all of today's unstarted games, at the present moment rather than the rule's window."""
    now = pd.Timestamp.now(tz="UTC")
    day = day or now.tz_convert("America/New_York").strftime("%Y-%m-%d")
    sched, rules, fz, logs = schedule(), load_rules(), json.loads(COEF.read_text()), load_logs()
    fp = LIVE / f"test_run_{now.strftime('%Y%m%dT%H%M')}.jsonl"
    tag = f"_test{now.strftime('%H%M')}"
    seen = set()
    for key, window, nominal, tip, g in decisions(sched, day):
        if tip is not None and tip <= now:
            continue
        slot = (window, tip) if window in ("T30G",) else key
        if slot in seen:
            continue
        seen.add(slot)
        print(key, run_decision(window, tip, g, nominal, sched, rules, fz, logs, picks_fp=fp, now_tag=tag), flush=True)
    d = read_jsonl(fp)
    print(f"\n{len(d)} test picks -> {fp.name}")
    if len(d):
        print(d[["rule", "who", "side", "point", "book", "price", "ev"]].to_string())
    return d


def plan(day=None):
    day = day or pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    d = decisions(schedule(), day)
    cost = sum({"NOON": 1, "T30G": 1, "T30P": 2, "T60P": 2}[x[1]] for x in d)
    print(f"{day}: {len(d)} decisions, about {cost} credits")
    for key, w, n, tip, g in d:
        print(f"  {iso(n)}  {w:5s} {key}")


def register():
    with gate._approvals_lock():
        a = gate._load_approvals()
        if any(o["id"] == OP for o in a["operations"]):
            print(OP, "already registered")
            return
        a["operations"].append(dict(id=OP, status="approved", endpoint="/v4/sports/basketball_nba/*", fixed_params=BASE, free_params=["markets"],
                                    max_requests=int(os.environ.get("LIVE_REQUEST_CAP", 4000)), max_credits=int(os.environ.get("LIVE_CREDIT_CAP", 8000)), approved_by="owner (app setup)",
                                    approved_at=iso(pd.Timestamp.now(tz="UTC")), approval_note="Live picks for the six WINNER markets at current odds: 1 credit per market per call",
                                    requests_done=0, credits_spent=0))
        gate._save_approvals(a)
    print("registered", OP)


# ---------------------------------------------------------------- settlement
def box_player(who, box, known) -> str | None:
    """The quoted player's row name in this game's box score. A name known to the logs must match exactly, so a player who sat
    out is never graded on a similar name (Jaylin / Jalen Williams). Only a name the logs do not know (a feed spelling such as
    Ron Holland) may use the close match."""
    n = props.norm_name(who)
    exact = {props.norm_name(x): x for x in box.PLAYER_NAME}
    return exact[n] if n in exact else None if n in known else props.match_names([who], box.PLAYER_NAME.tolist())[who]


def settle_table(p: pd.DataFrame, sched: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    """Result per logged pick. Game not final = pending. Player not in the box score, or 0 minutes = void, not a bet."""
    s = sched.set_index("gameId")
    known = {props.norm_name(x) for x in logs.PLAYER_NAME.unique()}
    by_game = {k: v for k, v in logs.groupby("GAME_ID")}
    res, state = [], []
    for r in p.itertuples():
        g = s.loc[r.game_id] if r.game_id in s.index else None
        if g is None or g.gameStatus != 3:
            res.append(np.nan)
            state.append("void" if g is not None and g.get("postponedStatus") == "Y" else "pending")
            continue
        if r.market in ("h2h", "totals"):
            res.append(gm.grade(r.market, r.side, r.point, g.homeTeam_score, g.awayTeam_score, True))
            state.append("graded")
            continue
        box = by_game.get(r.game_id)
        hit = box_player(r.who, box, known) if box is not None else None
        row = box[box.PLAYER_NAME == hit] if hit else None
        if row is None or row.empty or not (row.MIN.iloc[0] or 0) > 0:
            res.append(np.nan)
            state.append("void")
            continue
        actual = float(row.REB.iloc[0] + row.AST.iloc[0]) if r.market == "player_rebounds_assists" else float(row[PROP_MARKETS[r.market]].iloc[0])
        v = np.sign(actual - r.point)
        res.append(float(v if r.side == "over" else -v))
        state.append("graded")
    out = p.copy()
    out["result"], out["state"] = res, state
    out["profit"] = settle_profit(out.result, out.dec)
    return out


def refresh_results():
    """Free: current-season schedule, player and team box scores from stats.nba.com."""
    import fetch_results
    fetch_results.OUT = ROOT / "data" / "results"
    fetch_results.OUT.mkdir(parents=True, exist_ok=True)
    sys_argv, sys.argv = sys.argv, ["fetch_results", SEASON, "--refresh-current"]
    try:
        fetch_results.main()
    finally:
        sys.argv = sys_argv


def settle(refresh=True):
    if refresh:
        refresh_results()
    p = read_jsonl(PICKS)
    if p.empty:
        print("no picks logged yet")
        return
    t = settle_table(p, schedule(), load_logs([SEASON]))
    t.to_csv(LIVE / "picks_graded.csv", index=False)
    return t


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "plan"
    {"register": register, "plan": lambda: plan(a[1] if len(a) > 1 else None), "tick": tick, "loop": loop, "now": now_test,
     "settle": settle, "results": refresh_results}[cmd]()
