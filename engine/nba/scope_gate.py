"""Client acceptance logic from `NBA Scope.pdf` (3 pages, vector-outlined text, read visually 2026-10-25). Single source of truth.

Scope §2 ("same as MLB"): a market is a WINNER only if, on out-of-sample / holdout data, priced at the scope books:
  * Positive ROI, AND
  * Minimum +3% ROI ("break-even +0.5-1% does not count"), AND
  * Enough sample: 500+ graded bets with ROI above the floor, OR under 500 with the 95% CI lower bound above zero.
  "ROI is the gate, win rate is the headline."
  Statuses: WINNER (shipped, recommended) / SHOWN, NOT RECOMMENDED (visible but flagged) / FAIL (documented, cause + lever).
Scope §3: NBA ships as a sellable sport only if at least 5 markets clear the WINNER bar.
Scope §1: best available price across DraftKings, FanDuel, BetMGM, Caesars, ESPN BET, Hard Rock, Fanatics, BetRivers,
  bet365, Betr at the time the pick is made (not one book, not offshore).
Scope §5: the +3% bar is measured only on the ONE chosen pick window's picks.

Readings of ambiguous points (identical to the MLB readings the client accepted; see NBA_REQUIREMENTS.md A1-A7):
  A1  "Minimum +3%" is inclusive: ROI >= 3.00% passes, 2.99% does not.
  A2  The +3% floor applies on BOTH sample arms (bullets joined by AND).
  A3  The 95% CI is the more conservative (lower) of the per-bet normal CI and a bootstrap over whole slate-days.
  A4  ROI = net profit / total stake, flat 1 unit; push = graded bet with 0 profit; void (DNP, postponed) = not a bet.
  A5  FAIL = no valid priced sample at the scope books or ROI <= 0; SHOWN_NOT_RECOMMENDED = positive but below the bar.
"""
from __future__ import annotations

import numpy as np

SCOPE_BOOKS = ['DraftKings', 'FanDuel', 'BetMGM', 'Caesars', 'ESPN BET', 'Hard Rock', 'Fanatics', 'BetRivers', 'bet365', 'Betr']
# The Odds API bookmaker keys. bet365 (US) and Betr (US) have no Odds API feed (only bet365_au / betr_au; checked for MLB
# 2026-10-21, re-check via the free /sports-independent bookmaker list when the first NBA pull returns). Caesars = williamhill_us.
ODDS_API_KEYS = {
    'DraftKings': ['draftkings'], 'FanDuel': ['fanduel'], 'BetMGM': ['betmgm'], 'Caesars': ['williamhill_us'],
    'ESPN BET': ['espnbet'], 'Hard Rock': ['hardrockbet'], 'Fanatics': ['fanatics'], 'BetRivers': ['betrivers'],
    'bet365': [], 'Betr': [],
}
SCOPE_KEYS = sorted(k for v in ODDS_API_KEYS.values() for k in v)
REFERENCE_KEYS = ['pinnacle']   # sharp reference for fair price only; never a bet price

ROI_FLOOR = 0.03
N_LARGE = 500
WINNER, SHOWN, FAIL = 'WINNER', 'SHOWN_NOT_RECOMMENDED', 'FAIL'
MIN_WINNERS_TO_SHIP = 5

# Scope §5 windows. Clock windows are US/Eastern on the slate date; T-x are minutes before scheduled tip.
WINDOWS = {'AM9': ('clock', '09:00'), 'NOON': ('clock', '12:00'),
           'T180': ('rel', 180), 'T60': ('rel', 60), 'T30': ('rel', 30), 'T15': ('rel', 15)}

# Scope §4 markets: player props + game markets ("and any others already built": turnovers exists in the logged build).
MARKETS = {
    'player_points': 'points', 'player_rebounds': 'rebounds', 'player_assists': 'assists', 'player_threes': 'threes',
    'player_steals': 'steals', 'player_blocks': 'blocks', 'player_points_rebounds_assists': 'pra',
    'player_turnovers': 'turnovers', 'h2h': 'moneyline', 'spreads': 'spread', 'totals': 'total',
}


def normal_ci(profit, z=1.959964):
    p = np.asarray(profit, float)
    n = len(p)
    if n < 2:
        return (-np.inf, np.inf)
    m, se = p.mean(), p.std(ddof=1) / np.sqrt(n)
    return (m - z * se, m + z * se)


def cluster_bootstrap_ci(profit, clusters, n_boot=2000, seed=20261025, alpha=0.05):
    """Percentile CI of ROI resampling whole clusters (slate dates) with replacement."""
    p = np.asarray(profit, float)
    if len(p) < 2:
        return (-np.inf, np.inf)
    _, idx = np.unique(np.asarray(clusters).astype(str), return_inverse=True)
    k = idx.max() + 1
    if k < 2:
        return (-np.inf, np.inf)
    s = np.bincount(idx, weights=p, minlength=k)
    c = np.bincount(idx, minlength=k).astype(float)
    draw = np.random.default_rng(seed).integers(0, k, size=(n_boot, k))
    roi = s[draw].sum(1) / c[draw].sum(1)
    return (float(np.quantile(roi, alpha / 2)), float(np.quantile(roi, 1 - alpha / 2)))


def summarize(profit, result=None, clusters=None, dec=None):
    """profit per graded bet (win dec-1, loss -1, push 0). result +1/-1/0 optional."""
    p = np.asarray(profit, float)
    n = len(p)
    r = np.sign(p) if result is None else np.asarray(result)
    out = dict(n=n, wins=int((r > 0).sum()), losses=int((r < 0).sum()), pushes=int((r == 0).sum()),
               stake=float(n), profit=float(p.sum()), roi=float(p.mean()) if n else float('nan'))
    decided = out['wins'] + out['losses']
    out['win_rate'] = out['wins'] / decided if decided else float('nan')
    out['avg_dec'] = float(np.mean(dec)) if dec is not None and n else float('nan')
    out['ci_normal'] = normal_ci(p) if n else (float('nan'),) * 2
    out['ci_cluster'] = cluster_bootstrap_ci(p, clusters) if (clusters is not None and n) else out['ci_normal']
    out['ci_lo'] = min(out['ci_normal'][0], out['ci_cluster'][0]) if n else float('nan')
    out['ci_hi'] = max(out['ci_normal'][1], out['ci_cluster'][1]) if n else float('nan')
    return out


def verdict(n, roi, ci_lo, has_valid_data=True):
    """Scope §2 WINNER bar plus the A5 split of non-winners. Returns (status, reason)."""
    if not has_valid_data or not n:
        return FAIL, 'no valid priced sample at the scope books'
    if roi is None or not np.isfinite(roi):
        return FAIL, 'ROI is missing or invalid'
    if roi <= 0:
        return FAIL, f'ROI {roi:+.2%} is not positive'
    if roi < ROI_FLOOR:
        return SHOWN, f'ROI {roi:+.2%} is positive but below the +3% floor'
    if n >= N_LARGE:
        return WINNER, f'n={n} >= 500 and ROI {roi:+.2%} >= +3%'
    if ci_lo is not None and np.isfinite(ci_lo) and ci_lo > 0:
        return WINNER, f'n={n} < 500, ROI {roi:+.2%} >= +3% and 95% CI lower bound {ci_lo:+.2%} > 0'
    return SHOWN, f'n={n} < 500 and 95% CI lower bound is not above zero'


def verdict_revised(n, roi, ci_lo, has_valid_data=True, roi_floor=ROI_FLOOR):
    """Client-approved revised rule (REVISED_CLIENT_APPROVED_SCOPE.md, 2026-10-27): ROI >= floor AND 95% CI lower bound
    > 0 on unseen data; the 500-bet path is removed. roi_floor=0.01 is the +1% sensitivity tier only."""
    if not has_valid_data or not n:
        return FAIL, 'no valid priced sample at the scope books'
    if roi is None or not np.isfinite(roi):
        return FAIL, 'ROI is missing or invalid'
    if roi <= 0:
        return FAIL, f'ROI {roi:+.2%} is not positive'
    if roi < roi_floor:
        return SHOWN, f'ROI {roi:+.2%} is positive but below the {roi_floor:+.0%} floor'
    if ci_lo is not None and np.isfinite(ci_lo) and ci_lo > 0:
        return WINNER, f'ROI {roi:+.2%} >= {roi_floor:+.0%} and 95% CI lower bound {ci_lo:+.2%} > 0'
    return SHOWN, f'95% CI lower bound is not above zero (n={n})'


def verdict_final(n, roi, ci_lo, has_valid_data=True):
    """Final client-approved shipping rule (FINAL_SHIPPING_RULE.md, 2026-10-27): path A = ROI >= +3% AND 95% CI-lo > 0;
    path B = ROI >= +1% AND n >= 500. Chosen after the 2025-26 results were known (see the file's disclosure)."""
    if not has_valid_data or not n:
        return FAIL, 'no valid priced sample at the scope books'
    if roi is None or not np.isfinite(roi):
        return FAIL, 'ROI is missing or invalid'
    if roi <= 0:
        return FAIL, f'ROI {roi:+.2%} is not positive'
    a = roi >= ROI_FLOOR and ci_lo is not None and np.isfinite(ci_lo) and ci_lo > 0
    b = roi >= 0.01 and n >= N_LARGE
    if a or b:
        return WINNER, ('path A+B' if a and b else 'path A' if a else 'path B') + f': n={n}, ROI {roi:+.2%}'
    return SHOWN, f'n={n}, ROI {roi:+.2%}: neither path A (+3%, CI-lo > 0) nor path B (+1%, n >= 500)'


def verdict_two_season(n, roi, ci_lo, test_n, test_roi, has_valid_data=True):
    """Client-chosen shipping rule (Option 1, Two-Season Test, TWO_SEASON_RULE.md, chosen 2026-11-07): ROI >= +3% AND 95%
    CI lower bound > 0, both over 2024-25 + 2025-26 together, AND the 2025-26 season alone must also show ROI >= +3%.
    n, roi, ci_lo = the two seasons pooled; test_n, test_roi = 2025-26 alone. Chosen after the results were known."""
    if not has_valid_data or not n:
        return FAIL, 'no valid priced sample at the scope books'
    if roi is None or not np.isfinite(roi):
        return FAIL, 'ROI is missing or invalid'
    if roi <= 0:
        return FAIL, f'two-season ROI {roi:+.2%} is not positive'
    if not test_n or test_roi is None or not np.isfinite(test_roi):
        return SHOWN, 'no 2025-26 test-season bets'
    if test_roi < ROI_FLOOR:
        return SHOWN, f'2025-26 ROI {test_roi:+.2%} is below the +3% floor'
    if roi < ROI_FLOOR:
        return SHOWN, f'two-season ROI {roi:+.2%} is positive but below the +3% floor'
    if ci_lo is not None and np.isfinite(ci_lo) and ci_lo > 0:
        return WINNER, f'n={n}, two-season ROI {roi:+.2%}, 95% CI lower bound {ci_lo:+.2%}, 2025-26 ROI {test_roi:+.2%}'
    return SHOWN, f'n={n}: two-season 95% CI lower bound is not above zero'


def sport_verdict(statuses):
    """Scope §3: NBA ships only with >= 5 WINNER markets."""
    w = sum(1 for s in statuses if s == WINNER)
    return ('SHIPS' if w >= MIN_WINNERS_TO_SHIP else 'FAIL'), w


def american_to_decimal(a):
    a = np.asarray(a, float)
    return np.where(a > 0, 1 + a / 100.0, 1 + 100.0 / np.abs(a))


def settle(result, dec):
    """Flat 1 unit. result 1 win, -1 loss, 0 push, NaN void (-> NaN, not a bet)."""
    result = np.asarray(result, float)
    dec = np.asarray(dec, float)
    return np.where(result == 1, dec - 1, np.where(result == -1, -1.0, np.where(result == 0, 0.0, np.nan)))


def grade_over_under(actual, line, side):
    """Player prop / total grading: +1 win, -1 loss, 0 push (integer line), NaN if actual is missing."""
    actual, line = np.asarray(actual, float), np.asarray(line, float)
    over = np.where(actual > line, 1.0, np.where(actual < line, -1.0, 0.0))
    res = np.where(np.asarray(side) == 'over', over, -over)
    return np.where(np.isnan(actual), np.nan, res)


def no_vig_two_way(dec_a, dec_b, method='multiplicative'):
    """Fair probability of side A from a two-way market."""
    ia, ib = 1 / np.asarray(dec_a, float), 1 / np.asarray(dec_b, float)
    if method == 'multiplicative':
        return ia / (ia + ib)
    if method == 'power':   # solve ia^k + ib^k = 1
        lo, hi = np.full_like(ia, 0.5), np.full_like(ia, 2.0)
        for _ in range(60):
            k = (lo + hi) / 2
            s = ia ** k + ib ** k
            lo, hi = np.where(s > 1, k, lo), np.where(s > 1, hi, k)
        return ia ** ((lo + hi) / 2)
    raise ValueError(method)
