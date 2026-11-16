"""The ONLY module allowed to talk to The Odds API. Every billable call must match an approved operation.

Rules enforced in code (see NBA_API_CREDIT_LOG.md):
  * Free endpoints (/v4/sports, non-historical /v4/sports/{sport}/events) run without approval but are logged.
  * Every other endpoint needs an approval record in approvals/approvals.json whose status is "approved".
    The record fixes the endpoint pattern, allowed params, max request count and max credit spend.
  * Before each billable call the worst-case cost is computed from the official pricing rules; the call is refused
    if it would push the operation past its credit cap or request cap.
  * No automatic retries on billable endpoints (a failed call is logged and raised).
  * After each call x-requests-last is compared with the estimate; if it is higher, the operation is frozen
    ("halted") and every later call is refused until a human edits the approval.
  * Raw responses are cached (key-free file names) so a re-run never pays twice.
  * Access is ONLY through the client's proxy (ODDS_API_BASE, default below). The proxy token (ODDS_PROXY_TOKEN, from the
    environment or .env) is sent in the x-proxy-token header, never in the URL, and never logged.
  * The proxy's x-lock-at header (credit level at which the project locks) is a hard ceiling: a call whose estimate would
    reach it is refused.
"""
from __future__ import annotations

import contextlib
import fnmatch
import gzip
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("BASELINE_HOME") or Path(__file__).resolve().parents[2])
CACHE = ROOT / "data" / "raw" / "oddsapi"
APPROVALS = ROOT / "approvals" / "approvals.json"
LEDGER = ROOT / "logs" / "odds_api_ledger.jsonl"

FREE_PATTERNS = [r"^/usage/?$", r"^/v4/sports/?$", r"^/v4/sports/[^/]+/events/?$"]
HISTORICAL_MULT = 10
last_headers: dict = {}
lock_state: dict = {}   # latest x-requests-used / x-lock-at seen from the proxy


class ApprovalError(RuntimeError):
    pass


class UnbilledFailure(RuntimeError):
    """A billable call failed and the free /usage balance proves it cost nothing; the same request may be issued again."""


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, "")
    if not v:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith(name + "="):
                    v = line.split("=", 1)[1].strip()
    return v or default


def _token() -> str:
    return _env("ODDS_PROXY_TOKEN")


def _base() -> str:
    base = _env("ODDS_API_BASE")                             # proxy URL lives only in .env
    if not base:
        raise ApprovalError("ODDS_API_BASE not set (.env)")
    return base.rstrip("/")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(**rec) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _now(), **rec}
    line = (json.dumps(rec) + "\r\n").encode("utf-8")        # one binary write (text mode split long lines)
    with _file_lock(LEDGER.with_suffix(".lock")):            # concurrent jobs interleaved appends (2026-10-29)
        with open(LEDGER, "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())                              # power cuts: a billed call must never lose its line


def is_free(path: str) -> bool:
    return any(re.match(p, path) for p in FREE_PATTERNS)


def n_regions(params: dict) -> int:
    """Official rule: bookmakers take priority over regions; each group of 10 bookmakers = 1 region."""
    if params.get("bookmakers"):
        n = len([b for b in str(params["bookmakers"]).split(",") if b])
        return -(-n // 10)
    return len([r for r in str(params.get("regions", "")).split(",") if r]) or 1


def estimate_cost(path: str, params: dict) -> int:
    """Worst-case credits for one call (official v4 pricing, checked 2026-10-25)."""
    if is_free(path):
        return 0
    hist = path.startswith("/v4/historical/")
    if re.search(r"/events/?$", path):                       # historical events list
        return 1
    if path.endswith("/participants") or path.endswith("/markets"):
        return 1
    if path.endswith("/scores"):
        return 2 if params.get("daysFrom") else 1
    markets = len([m for m in str(params.get("markets", "h2h")).split(",") if m])
    return (HISTORICAL_MULT if hist else 1) * markets * n_regions(params)


@contextlib.contextmanager
def _approvals_lock(timeout: float = 60.0):
    """Cross-process lock so concurrent fetch jobs never lose an approvals.json update."""
    with _file_lock(APPROVALS.with_suffix(".lock"), timeout):
        yield


@contextlib.contextmanager
def _file_lock(lock: Path, timeout: float = 60.0):
    """Exclusive lock file (O_CREAT | O_EXCL), shared by threads and processes; stale after 300 s."""
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):           # Windows: lock being deleted by its holder
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:                         # released between open and stat: retry
                continue
            if age > 300:                                     # stale lock from a crashed process
                lock.unlink(missing_ok=True)
            elif time.time() - t0 > timeout:
                raise ApprovalError(f"{lock.name} lock timeout")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def _load_approvals() -> dict:
    if not APPROVALS.exists():
        return {"operations": []}
    for attempt in range(40):                                 # Windows: os.replace by another process denies reads
        try:
            return json.loads(APPROVALS.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.25)


def _atomic_write(fp: Path, data: bytes) -> None:
    """Write via a fsynced temp file + os.replace, so a power cut leaves either the old or the new file, never zeros."""
    tmp = fp.with_name(fp.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(20):                                 # Windows: a reader/antivirus can briefly hold fp open
        try:
            os.replace(tmp, fp)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.25)


def _save_approvals(a: dict) -> None:
    APPROVALS.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(APPROVALS, json.dumps(a, indent=2).encode("utf-8"))


def _match(op: dict, path: str, params: dict) -> bool:
    if not fnmatch.fnmatch(path, op["endpoint"]):
        return False
    for k, allowed in op.get("fixed_params", {}).items():   # must equal exactly
        if str(params.get(k, "")) != str(allowed):
            return False
    extra = set(params) - set(op.get("fixed_params", {})) - set(op.get("free_params", []))
    if extra:
        return False
    lo, hi = op.get("date_range", [None, None])
    if lo and params.get("date") and not (lo <= params["date"] <= hi):
        return False
    return True


def _cache_path(path: str, params: dict) -> Path:
    q = urllib.parse.urlencode(sorted(params.items()))
    return CACHE / (hashlib.sha1(f"{path}?{q}".encode()).hexdigest() + ".json.gz")


def cached(path: str, params: dict):
    fp = _cache_path(path, params)
    if fp.exists():
        with gzip.open(fp, "rt", encoding="utf-8") as f:
            return json.load(f)
    return None


def get(path: str, op_id: str | None = None, **params):
    """Fetch path with params. Returns cached data when present (costs nothing).
    `_tag` (optional) is a local cache label only, never sent to the API: it lets the same request be fetched again at a
    different decision time (e.g. the same event's props at T-60 and at T-30) without being served from the cache."""
    tag = params.pop("_tag", None)
    ckey = {**params, "_tag": tag} if tag else params
    no_cache = path.rstrip("/") == "/usage"                  # a balance must always be live
    hit = None if no_cache else cached(path, ckey)
    if hit is not None:
        return hit
    est = estimate_cost(path, params)
    approvals = _load_approvals()
    op = None
    if est > 0:
        op = next((o for o in approvals["operations"] if o["id"] == op_id), None)
        reason = None
        if op is None:
            reason = f"no approval record '{op_id}'"
        elif op.get("status") != "approved":
            reason = f"operation {op_id} status is {op.get('status')}"
        elif not _match(op, path, params):
            reason = f"request is outside the approved scope of {op_id}"
        elif op.get("requests_done", 0) + 1 > op["max_requests"]:
            reason = f"{op_id} request cap {op['max_requests']} reached"
        elif op.get("credits_spent", 0) + est > op["max_credits"]:
            reason = f"{op_id} credit cap {op['max_credits']} would be exceeded"
        if reason:
            _log(event="REJECTED", op_id=op_id, path=path, params=params, est=est, reason=reason)
            raise ApprovalError(reason)
    token = _token()
    if not token:
        raise ApprovalError("ODDS_PROXY_TOKEN not set (.env)")
    if est > 0 and lock_state.get("lock_at") and lock_state.get("used") is not None:
        if lock_state["used"] + est >= lock_state["lock_at"]:
            _log(event="REJECTED", op_id=op_id, path=path, params=params, est=est, reason="would reach proxy lock")
            raise ApprovalError(f"estimate {est} would reach the proxy lock at {lock_state['lock_at']}")
    q = urllib.parse.urlencode(sorted(params.items()))
    url = f"{_base()}{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(url, headers={"x-proxy-token": token, "User-Agent": "nba-validation/0.1"})
    used_before = lock_state.get("used")
    attempts = 3 if est == 0 else 1                          # never auto-retry a billable call
    data, hdr, err = None, {}, None
    for a in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                hdr = {k.lower(): v for k, v in r.headers.items()}
                data = json.loads(r.read().decode())
            err = None
            break
        except urllib.error.HTTPError as e:
            hdr = {k.lower(): v for k, v in e.headers.items()}
            err = f"HTTP {e.code}: {e.read().decode()[:200]}"
        except Exception as e:                                # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        time.sleep(2)
    last_headers.clear()
    last_headers.update(hdr)
    actual = int(hdr.get("x-requests-last", 0) or 0)
    remaining = hdr.get("x-requests-remaining")
    if hdr.get("x-requests-used") is not None:
        lock_state["used"] = int(float(hdr["x-requests-used"]))
    if hdr.get("x-lock-at") is not None:
        lock_state["lock_at"] = int(float(hdr["x-lock-at"]))
    _log(event="EXECUTED" if err is None else "FAILED", op_id=op_id, path=path, params=params, est=est,
         actual=actual, remaining=remaining, used=hdr.get("x-requests-used"), lock_at=hdr.get("x-lock-at"), error=err)
    if est == 0 and actual > 0:                               # a "free" call was billed: stop everything
        _log(event="HALTED", op_id=None, reason=f"free endpoint {path} billed {actual}")
        raise ApprovalError(f"free endpoint {path} unexpectedly billed {actual} credits; all Odds API work stopped")
    unbilled = False
    if op is not None and err is not None:
        # Verify against the free balance whether the failed call was charged. Unverifiable -> treat as billed and halt.
        try:
            u = get("/usage")
            unbilled = used_before is not None and int(u["used"]) == used_before
        except Exception:                                     # noqa: BLE001
            unbilled = False
        _log(event="FAILED_UNBILLED" if unbilled else "HALTED", op_id=op_id, path=path, params=params,
             reason=f"failed call; balance before {used_before}, after {lock_state.get('used')}")
    if op is not None:
        with _approvals_lock():
            approvals = _load_approvals()
            op = next(o for o in approvals["operations"] if o["id"] == op_id)
            if err is not None and not unbilled:
                op["status"] = "halted"
                op["halt_reason"] = f"failed call could not be verified as unbilled: {path} {params} ({err})"
            if unbilled:
                _save_approvals(approvals)
                raise UnbilledFailure(err)
            op["requests_done"] = op.get("requests_done", 0) + 1
            op["credits_spent"] = op.get("credits_spent", 0) + actual
            op["last_remaining"] = remaining
            if actual > est:
                op["status"] = "halted"
                op["halt_reason"] = f"actual cost {actual} > estimate {est} on {path} {params}"
                _log(event="HALTED", op_id=op_id, reason=op["halt_reason"])
            _save_approvals(approvals)
    if err is not None:
        raise RuntimeError(err)
    if no_cache:
        if isinstance(data, dict) and "used" in data and "cap" in data:
            lock_state["used"], lock_state["lock_at"] = int(data["used"]), int(data["cap"])
        return data
    CACHE.mkdir(parents=True, exist_ok=True)
    _atomic_write(_cache_path(path, ckey), gzip.compress(json.dumps(data).encode("utf-8")))
    return data


def run_resilient(items, fn, max_consecutive=5, base_wait=30):
    """Call fn(i, item) for each item. A failure proven unbilled (UnbilledFailure) is retried in a later pass after a wait;
    max_consecutive unbilled failures in a row stop the run. Any other error (including a halt) propagates at once."""
    pending, consecutive, n = list(items), 0, 0
    while pending:
        failed = []
        for item in pending:
            try:
                fn(n, item)
                consecutive = 0
            except UnbilledFailure as e:
                consecutive += 1
                failed.append(item)
                print(f"unbilled failure #{consecutive}: {e}; waiting {base_wait * consecutive}s", flush=True)
                if consecutive >= max_consecutive:
                    raise RuntimeError(f"{consecutive} unbilled failures in a row; stopping (nothing was charged)") from e
                time.sleep(base_wait * consecutive)
            n += 1
        if len(failed) == len(pending):
            raise RuntimeError("no progress in a full pass; stopping")
        pending = failed
