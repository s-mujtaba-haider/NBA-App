# NBA shipping rule: the Two-Season Test (Option 1), chosen by the client

Source: the client's reply to `NBA_Proposed_Solution.pdf`, relayed by the project owner on 2026-11-07: choose Options 1 and 4 if
combining them raises ROI, otherwise Option 1. Later changes are dated amendments below, never edits.
Implementation: `src/nba/scope_gate.py::verdict_two_season`, `two_season_rule/engine.py`. Recount: `python two_season_rule/run.py`.

## Rule

A market is a WINNER when all three hold:

| Check | Bar | Measured on |
|---|---|---|
| ROI | at least +3% | 2024-25 + 2025-26 together |
| 95% CI lower bound | above 0 | 2024-25 + 2025-26 together |
| ROI | at least +3% | 2025-26 alone |

* NBA ships with at least 5 WINNERs out of the 23 counted markets. Failed markets stay in the count.
* All 8 books with a feed; best price at pick time; each market's frozen rule and pick time; no refitting, no new tuning.
* CI = the official 95% CI: the lower of the per-bet normal bound and the slate-day bootstrap (2,000 draws, seed 20261025).
* FAIL = no valid sample or two-season ROI at or below 0. Otherwise SHOWN, NOT RECOMMENDED.

## Combination test (Option 1 with Option 4)

Fixed before the combined figures were computed (`two_season_rule/combine_test.py`): a union or intersection of the two market
lists replaces Option 1 only if its 2025-26 ROI is strictly higher and it keeps at least 5 WINNERs.
Result: Option 1 +8.83%, union +8.51%, intersection +8.31%. **Decision: Option 1 alone.**

## Disclosure (must accompany every use of this rule)

* The rule was chosen after the results were known. It adds no evidence by itself.
* The client's strict count (ROI at least +3% and CI lower bound above 0 on 2025-26 alone) stays 3 and is reported beside this count.
* 2024-25 helped build the rules, so it is not unseen data. That is why 2025-26 alone must also clear +3%.
* Moneyline passes with a CI lower bound of only +0.1%, and falls below 0 once live 2026-27 bets are added.
* The live record decides what holds up. Past results do not guarantee future results.

## Amendments

* **2026-11-07, audit correction.** Two 2024-25 rebounds ledger rows were graded although the player did not play, and are void
  under the scope's reading A4: Steven Adams on 2025-03-17 (0 minutes) and Jaylin Williams on 2025-03-29 (a close-name match to
  Jalen Williams). `engine.py` removes them from the count; the ledger file stays as written. Rebounds over the two seasons moves
  from 1,950 bets, +7.53%, CI low +3.02% to 1,948 bets, +7.44%, CI low +2.93%. No status changes and no 2025-26 figure changes.
