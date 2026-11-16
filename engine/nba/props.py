"""Player-prop quotes from historical event-odds responses, matched to box scores and graded.

Matching: the Odds API names players in `description`. Names are normalised (accents, punctuation, Jr/Sr/II/III removed)
and matched to the box-score players of the two teams in that game; a close fuzzy match (difflib ratio >= 0.88) is used
only within that game's two rosters. A quoted player absent from the box score did not play -> void (not a bet).
A name that matches nobody on either roster is reported as unmatched, never graded.

Fair reference per (player, market, line): Pinnacle no-vig at the same line, else the leave-one-out median no-vig of the
other scope books at the same line. Bets only compare quotes on the same line.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import numpy as np
import pandas as pd

from nba.scope_gate import SCOPE_KEYS, american_to_decimal, grade_over_under, no_vig_two_way, settle

STAT = {"player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST", "player_threes": "FG3M",
        "player_steals": "STL", "player_blocks": "BLK", "player_turnovers": "TOV",
        "player_points_rebounds_assists": "PRA"}
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'\-]", "", s)
    s = SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def match_names(quoted: list[str], roster: list[str]) -> dict:
    """quoted name -> roster name, or None (not found = did not play or unmatched)."""
    rn = {norm_name(r): r for r in roster}
    out = {}
    for q in quoted:
        n = norm_name(q)
        if n in rn:
            out[q] = rn[n]
            continue
        best = difflib.get_close_matches(n, list(rn), n=1, cutoff=0.88)
        out[q] = rn[best[0]] if best else None
    return out


def parse_event(resp: dict, decision: pd.Timestamp) -> pd.DataFrame:
    """Long table: book, market, player, side, point, price, last_update. Quotes stamped after `decision` are dropped."""
    ev = resp.get("data") or {}
    rows = []
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] not in STAT or pd.Timestamp(mk["last_update"]) > decision:
                continue
            for o in mk["outcomes"]:
                side = o["name"].lower()
                if side in ("over", "under") and o.get("point") is not None:
                    rows.append((ev.get("id"), bk["key"], mk["key"], o["description"], side, float(o["point"]),
                                 o["price"], mk["last_update"]))
    q = pd.DataFrame(rows, columns=["event_id", "book", "market", "player", "side", "point", "price", "last_update"])
    q = q.drop_duplicates(["book", "market", "player", "side", "point"])
    q["dec"] = american_to_decimal(q.price) if len(q) else []
    q["is_scope"] = q.book.isin(SCOPE_KEYS)
    return q


def fair_and_ev(q: pd.DataFrame, devig: str = "multiplicative") -> pd.DataFrame:
    """Add p_over_ref (no-vig, same line), EV per scope quote. q may hold many events/windows (keys below)."""
    k = ["window", "event_id", "market", "player", "point"]
    o = q[q.side == "over"].set_index(k + ["book"])
    u = q[q.side == "under"].set_index(k + ["book"])
    pr = o[["dec"]].join(u[["dec"]], lsuffix="_o", rsuffix="_u", how="inner")
    pr["p_over"] = no_vig_two_way(pr.dec_o.values, pr.dec_u.values, devig) if len(pr) else []
    pr = pr.reset_index()
    pin = pr[pr.book == "pinnacle"].set_index(k)["p_over"].rename("p_over_pin")
    sc = pr[pr.book != "pinnacle"][k + ["book", "p_over"]]
    c = q[q.is_scope].copy()
    loo = c[k + ["book"]].drop_duplicates().merge(sc, on=k, suffixes=("", "_ref"))
    lg = loo[loo.book != loo.book_ref].groupby(k + ["book"])["p_over"]
    loo = lg.median().rename("p_over_cons")
    n_cons = lg.size().rename("n_cons")                      # number of other scope books behind the consensus
    c = c.join(pin, on=k).join(loo, on=k + ["book"]).join(n_cons, on=k + ["book"])
    c["ref"] = np.where(c.p_over_pin.notna(), "pinnacle", np.where(c.p_over_cons.notna(), "consensus", None))
    c["p_over_ref"] = c.p_over_pin.fillna(c.p_over_cons)
    c = c[c.ref.notna()].copy()
    # integer lines can push; the no-vig split is applied to the non-push mass (push mass ignored: conservative for EV)
    c["p_win"] = np.where(c.side == "over", c.p_over_ref, 1 - c.p_over_ref)
    c["ev"] = c.p_win * c.dec - 1
    return c


def grade_props(bets: pd.DataFrame, box: pd.DataFrame) -> pd.DataFrame:
    """bets need event game_id + matched box-score PLAYER_NAME in `box_name`. Unplayed -> void (dropped)."""
    box = box.assign(PRA=box.PTS + box.REB + box.AST).drop(columns=[c for c in ("season",) if c in bets], errors="ignore")
    b = bets.merge(box, left_on=["game_id", "box_name"], right_on=["GAME_ID", "PLAYER_NAME"], how="left")
    actual = np.full(len(b), np.nan)
    for m, col in STAT.items():
        sel = (b.market == m).values & b.PLAYER_NAME.notna().values
        actual[sel] = b.loc[sel, col].astype(float).values
    b["actual"] = actual
    b["result"] = grade_over_under(actual, b.point, b.side)
    b = b[b.result.notna()].copy()
    b["profit"] = settle(b.result, b.dec)
    return b
