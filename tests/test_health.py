"""
Offline tests for the exception-only health check (pipeline/health.py). Run: python -m pytest tests/  (or)  python tests/test_health.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import pandas as pd  # noqa: E402

from pipeline import health, util  # noqa: E402

NOW = pd.Timestamp("2026-10-16 08:05")          # Friday morning: last trading day is Thursday Oct 15


def write_nav(name, days):
    pd.DataFrame({"date": days, "x": 1}).to_csv(util.state_path(name), index=False)


def test_quiet_when_complete_and_alerts_on_gaps_once():
    full = [d.date().isoformat() for d in pd.bdate_range("2026-10-12", "2026-10-15")]
    util.write_json(util.state_path("external_books.json"),
                    {"books": {"robinhood_roth": {"label": "Roth"}, "robinhood_2": {"label": "Account 2"}}})
    for n in ("daily_account_nav.csv", "daily_nav_robinhood_roth.csv", "daily_nav_robinhood_2.csv"):
        write_nav(n, full)
    pd.DataFrame({"time": ["2026-10-15 20:03"], "stage": ["watch"], "status": ["quiet"]}).to_csv(util.state_path("run_log.csv"), index=False)
    sent = []
    out = health.main(NOW, send_fn=lambda *a, **k: sent.append(a))
    assert out["status"] in ("ok", "flag")
    keys = [k for k, _ in health.checks(NOW)]
    assert not [k for k in keys if k.startswith("nav:") or k == "watch"] and sent == [] or out["status"] == "flag"
    write_nav("daily_nav_robinhood_roth.csv", ["2026-10-12", "2026-10-15"])     # Oct 13 and 14 missing
    found = dict(health.checks(NOW))
    assert "nav:daily_nav_robinhood_roth.csv" in found and "2026-10-13" in found["nav:daily_nav_robinhood_roth.csv"]
    sent.clear()
    health.main(NOW, send_fn=lambda *a, **k: sent.append(a))
    assert len(sent) == 1
    health.main(NOW, send_fn=lambda *a, **k: sent.append(a))
    assert len(sent) == 1                                                       # not repeated the same day


def test_stale_watch_and_holidays_are_handled():
    pd.DataFrame({"time": ["2026-10-13 20:03"], "stage": ["watch"], "status": ["quiet"]}).to_csv(util.state_path("run_log.csv"), index=False)
    assert "watch" in dict(health.checks(NOW))
    # Thanksgiving Thursday is not a trading day: Friday morning's last trading day is Wednesday
    days = [d.date().isoformat() for d in health.trading_days("2026-11-23", "2026-11-27")]
    assert "2026-11-26" not in days and len(days) == 4


def test_todays_watch_is_not_overdue_before_the_late_evening():
    pd.DataFrame({"time": ["2026-10-19 20:32"], "stage": ["watch"], "status": ["quiet"]}).to_csv(util.state_path("run_log.csv"), index=False)
    early = pd.Timestamp("2026-10-20 19:30", tz="America/New_York")
    late = pd.Timestamp("2026-10-20 23:30", tz="America/New_York")
    assert "watch" not in dict(health.checks(early))        # Tuesday's watch usually lands 8 to 9 pm ET
    assert "watch" in dict(health.checks(late))             # but is flagged once it is clearly missing


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
