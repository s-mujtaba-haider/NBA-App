"""Settings, read from environment variables and the .env file at the project root.

Two folders matter:
  APP_ROOT   the code and the frozen, read-only files (rules, track record ledgers, web build)
  HOME       writable data: results refreshed from stats.nba.com, live picks, database, Odds API cache and ledger.
             Defaults to APP_ROOT when run from source; the desktop build points it at %APPDATA%/Baseline.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    APP_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(APP_ROOT / ".env")
HOME = Path(os.getenv("BASELINE_HOME") or APP_ROOT)
os.environ["BASELINE_HOME"] = str(HOME)          # the engine reads the same variable
DATA_DIR = HOME / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ENGINE_DIR = APP_ROOT / "engine"
RULES_DIR = APP_ROOT / "data" / "rules"
LEDGER_DIR = APP_ROOT / "data" / "ledger"
WEB_DIST = APP_ROOT / "web" / "dist"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


def seed_home() -> None:
    """First start of an installed copy: copy the shipped results so the writable folder has a full history."""
    src = APP_ROOT / "data" / "results"
    dst = DATA_DIR / "results"
    if src.resolve() == dst.resolve() or not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.parquet"):
        if not (dst / f.name).exists():
            shutil.copy2(f, dst / f.name)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{(DATA_DIR / 'baseline.db').as_posix()}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


@dataclass
class Settings:
    app_name: str = "Baseline NBA API"
    version: str = "1.0.0"
    env: str = os.getenv("APP_ENV", "development")
    database_url: str = field(default_factory=_database_url)

    # Security
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    license_private_key: str = os.getenv("LICENSE_PRIVATE_KEY", "")
    legacy_hmac_secret: str = os.getenv("LEGACY_HMAC_SECRET", "")
    legacy_hmac_user_id: str = os.getenv("LEGACY_HMAC_USER_ID", "")
    # true: every data endpoint needs a valid license key (web deployments). false: open (local desktop use).
    require_api_key: bool = _bool("REQUIRE_API_KEY", False)

    # Live picks. AUTO_PICKS runs the decision windows on a timer; each window costs Odds API credits
    # (capped by the gate's approval record). Off by default: picks run when the owner presses "Run".
    auto_picks: bool = _bool("AUTO_PICKS", False)
    auto_results: bool = _bool("AUTO_RESULTS", True)       # free: stats.nba.com refresh + grading, every few hours
    results_every_hours: int = _int("RESULTS_EVERY_HOURS", 4)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def odds_configured(self) -> bool:
        return bool(os.getenv("ODDS_API_BASE") and os.getenv("ODDS_PROXY_TOKEN"))


settings = Settings()
