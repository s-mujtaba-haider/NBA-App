# Baseline · NBA

Picks, track record and bankroll simulation for the six NBA markets that passed the client's shipping rule.
One codebase runs as a **web app**, a **mobile-friendly site** and a **Windows desktop app** with a one-click installer.

| Market | Window | Bets (2024-25 + 2025-26) | ROI | 95% CI low | 2025-26 ROI |
|---|---|---|---|---|---|
| Game totals | T-30 | 555 | +9.9% | +2.0% | +14.8% |
| Player rebounds | T-30 | 1,948 | +7.4% | +2.9% | +7.2% |
| Player threes | T-60 | 674 | +17.0% | +6.5% | +15.4% |
| Rebounds + assists | T-30 | 1,058 | +11.4% | +5.0% | +6.7% |
| Player blocks | T-60 | 487 | +12.6% | +2.0% | +7.4% |
| Moneyline | 12:00 ET | 452 | +9.1% | +0.1% | +6.9% |

2025-26 (unseen season): 2,296 bets, +202.8 units, +8.8% ROI, 8 of 9 months in profit. Rule of record: the
Two-Season Test (ROI ≥ +3% and 95% CI lower bound > 0 over 2024-25 + 2025-26, and ROI ≥ +3% on 2025-26 alone).
The rule was chosen after the results were known; the strict count (2025-26 alone) is 3, and moneyline's CI lower
bound falls below 0 once live 2026-27 bets are added. The app shows these disclosures on the Record page and in the PDF report.

## What is in the app

| Page | What it does |
|---|---|
| **Board** | Today's slate: countdown to the next decision window, decision timeline (12:00 ET, T-60, T-30, tip-offs, now), every pick with best price and book, win probability against break-even, edge, grade and result; game tiles with window status. Any day can be opened. CSV and PDF export. |
| **Pick detail** | Why the pick was made: market fair price, player projection, stacked probability, break-even of the price; the player's previous games against the line; the market's record and frozen rule. |
| **Markets** | The six markets with ROI, CI, live record and trend; per market: equity curve, units by month, realised ROI by edge, calibration, recent picks. |
| **Record** | Combined and per-market equity since 2024-25 with season bands, market × month heatmap, results by book, rule disclosure, PDF report. |
| **Simulator** | Monte Carlo bankroll simulation (whole nights resampled, so same-night bets stay together): flat or % staking, horizon, simulations, price haircut, sample choice; fan chart, outcome histogram, chance of profit, drawdown, ruin. |
| **History** | Every graded bet with search, filters, paging and CSV export. |
| **Engine** | Odds feed and credit status, today's decision plan, run buttons (due windows, results refresh, test run) with progress, job history and live logs. |
| **License** | Sign in with email + license key; license status and devices. |

Also: ticker of the six markets, bottom status bar (feed, credits, auto picks, running job with progress and time left),
a log drawer, clickable notifications when runs finish, page transitions, and a bottom tab bar on phones.

## How picks are made

`engine/livepicks.py` is the live pick code of the research project, unchanged in logic: the frozen rule files in
`data/rules/`, quotes counted only if stamped at or before the decision, player numbers from earlier games only, the best
price across the 8 scope books, and the EV floor of each market. Results come free from stats.nba.com (`nba_api`);
picks are graded automatically (player not in the box score or 0 minutes = void).

Every Odds API call goes through `engine/nba/oddsapi_gate.py`: an approval record with request and credit caps
(`LIVE_CREDIT_CAP`, `LIVE_REQUEST_CAP`), no paid retries, a halt on any charge above the estimate, a ledger line per call,
and a response cache. About 37 credits cover a 7-game night. With `AUTO_PICKS=false` (default) nothing billable runs until
someone presses **Run** on the Engine page.

The track record (`data/ledger/bets.parquet`) is built from the research repo by `tools/build_ledger.py`, which checks
every market's bet count and ROI against the figures of record before writing. `data/ledger/replay_2026-27.csv` is the
2026-27 live season so far (same pick code on the stored pick-time snapshots); picks the app logs itself follow it.

## Run

```bash
pip install -r requirements.txt
copy .env.example .env                 # odds proxy URL + token for live picks (optional)
cd web && npm ci && npm run build && cd ..
uvicorn backend.app.main:app --port 8765
# open http://localhost:8765   (API docs: /docs)
```

Frontend development with hot reload: `cd web && npm run dev` (proxies `/api` to port 8765).

Desktop window: `pip install pywebview` then `python desktop/launcher.py`. It starts the server in-process on a free port
and opens a native window; without pywebview it opens the browser.

Tests: `python -m pytest -q` (record figures equal the figures of record, API, exports, simulation, license lifecycle,
pick-time quote filter).

## Licensing

Licenses have a start and an end date and are issued only by the owner:

```bash
python -m backend.app.cli create-user customer@example.com --days 365     # prints the key once
python -m backend.app.cli list-users
python -m backend.app.cli extend-user customer@example.com --end 2027-12-31
python -m backend.app.cli public-key --out desktop/license_public_key.pem  # ship with desktop builds
```

Or over HTTP with `X-Admin-Token` (`/api/admin/users`). The desktop app receives an Ed25519-signed token bound to the
device, verifies it with the bundled public key, refreshes it online on each start (so a revoked license stops), allows a
short offline grace period and detects a clock set backwards. A public key cannot create licenses, and editing the token
breaks the signature. On a hosted server set `REQUIRE_API_KEY=true` so every page needs a license key.

## Install and deploy

* **Windows installer:** `powershell -ExecutionPolicy Bypass -File installer\build.ps1 -LicenseServer https://your-server`
  builds the web app, bundles everything with PyInstaller and produces `installer\Output\Baseline_Setup_1.0.0.exe`:
  per-user install, no admin rights, shortcuts, launches when done, `/VERYSILENT` for no interaction at all. Writable
  data goes to `%APPDATA%\Baseline`.
* **Cloud:** `docker build -t baseline .` then run with the variables from `.env.example` and a volume on `/var/baseline`
  (AWS App Runner/ECS, Azure Container Apps, GCP Cloud Run, Render, Fly). `PORT` is honoured.

## Layout

| Path | Contents |
|---|---|
| `backend/app/` | FastAPI: `record.py` (track record, CI, equity, heatmap, calibration), `slate.py` (board, windows, picks, player form), `simulation.py`, `exporting.py` (CSV/PDF), `runner.py` (engine jobs and scheduler), `security.py` + `routers/auth.py` (licenses), `jobs.py`, `logbuffer.py`, `cli.py` |
| `engine/` | Pick engine: `livepicks.py`, `nba/` (pricing, projections, props, game markets, scope gate, credit gate), `fetch_results.py` |
| `data/rules/` | Frozen rule files and stack coefficients (read only) |
| `data/ledger/` | Track record ledgers and the figures of record |
| `data/results/` | Schedules and box scores 2023-24 to 2026-27 (refreshed by the app) |
| `web/` | React + TypeScript + Vite frontend, own chart components (d3-scale/d3-shape), self-hosted fonts |
| `desktop/` | Native window launcher and license activation |
| `installer/` | PyInstaller spec, Inno Setup script, one-step build |
| `tools/build_ledger.py` | Rebuilds the track record from the research repo, with checks |
| `tests/` | Test suite |
