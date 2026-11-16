import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# isolated writable home for every test run: own database, no live picks, no odds feed, no background refresh
_home = tempfile.mkdtemp(prefix="baseline_test_")
os.environ.update(BASELINE_HOME=_home, AUTO_RESULTS="false", AUTO_PICKS="false", ADMIN_TOKEN="test-admin",
                  ODDS_API_BASE="", ODDS_PROXY_TOKEN="", REQUIRE_API_KEY="false")
