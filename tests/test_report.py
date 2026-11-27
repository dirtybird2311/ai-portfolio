"""
Offline tests for the performance and statistics reports (pipeline/report.py): built from synthetic NAV files in
a temp folder with fake prices. Run: python -m pytest tests/  (or)  python tests/test_report.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import config, report, util  # noqa: E402

DAYS = pd.bdate_range("2026-09-28", "2026-10-15")


def seed_state():
    rng = np.random.default_rng(7)
    spy = 10000 * np.cumprod(1 + rng.normal(0.0004, 0.006, len(DAYS)))
    rec = 10000 * np.cumprod(1 + rng.normal(0.0012, 0.007, len(DAYS)))
    rows = [{"date": d.date().isoformat(), "since": "2026-09-28", "start_value": 10000.0, "record_value": round(r, 2),
             "record_return_pct": 0, "spy_return_pct": round((s / 10000 - 1) * 100, 2), "record_vs_spy_pct_pts": 0,
             "executed_value": round(r * 0.995, 2), "executed_return_pct": 0, "executed_vs_spy_pct_pts": 0,
             "record_basis": "planned trade dates"} for d, r, s in zip(DAYS, rec, spy)]
    pd.DataFrame(rows).to_csv(util.state_path("daily_account_nav.csv"), index=False)
    util.write_json(util.state_path("external_books.json"),
                    {"books": {"robinhood_roth": {"label": "Roth"}, "robinhood_2": {"label": "Account 2"}}})
    for name, mult in (("robinhood_roth", 1.0004), ("robinhood_2", 1.0003)):
        v = 6600 * np.cumprod(np.full(len(DAYS) - 5, mult))
        d = DAYS[5:]
        pd.DataFrame({"date": [x.date().isoformat() for x in d], "book_value": v, "cost": 6600.0, "book_return_pct": 0,
                      "spy_same_dollars_value": 6600 * np.cumprod(np.full(len(d), 1.0002)), "spy_return_pct": 0, "vs_spy_pct_pts": 0,
                      "stocks_return_pct": 0, "stocks_vs_spy_pct_pts": 0}).to_csv(util.state_path(f"daily_nav_{name}.csv"), index=False)
    tick = [f"S{i}" for i in range(40)]
    util.write_json(util.state_path("rebuild_history.json"), [
        {"date": "2026-09-27", "trade_date": "2026-09-28", "target": {**{t: 12.0 for t in tick[:8]}, "SPY": 4.0},
         "sectors": {t: ["A", "B"][i % 2] for i, t in enumerate(tick)}}])
    util.write_json(util.state_path("current_features.json"), {"date": "2026-10-09", "stocks": {t: {} for t in tick + [f"U{i}" for i in range(120)]}})


def loader(tick, start):
    idx = pd.bdate_range(start or "2026-04-01", "2026-10-15")
    rng = np.random.default_rng(len(tick))
    return pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, (len(idx), len(tick))), axis=0), index=idx, columns=list(tick))


def test_daily_sheet_has_numbers_and_no_stats():
    seed_state()
    html, md, ctx = report.build(weekly=False)
    assert "Paper record" in html and "Last 10 days" in html and "data:image/png" in html
    assert "Statistics" not in html and "Robinhood (combined)" in md and "Roth IRA" not in html and ctx["lead"] == ctx["record"] - ctx["spy"]


def test_weekly_report_sections_and_honesty_about_sample_size():
    seed_state()
    html, md, ctx = report.build(weekly=True, loader=loader, n_sims=200)
    for needle in ("Is the lead more than noise?", "Information ratio", "Chance noise alone", "Do we beat random picks? Three tests",
                   "Go-live readiness", "Too early to call"):
        assert needle in html, needle
    assert ctx["stats"]["n_days"] == len(DAYS) - 1 or ctx["stats"]["n_days"] == len(DAYS)
    pools = {r["pool"][:2] for r in ctx["random"] if r.get("ok")}
    assert pools == {"1.", "2.", "3."}, pools            # picks vs universe, picks vs shortlist, shortlist vs universe
    assert "Factor regression starts" in html          # fewer than 20 days: said, not faked


def test_verdict_thresholds():
    short = {"n_days": 14, "bootstrap": {"observed": 0.045, "lo": -0.004, "hi": 0.095, "p_noise": 0.04}}
    assert "Too early" in report.verdict(short)
    longer = {"n_days": 90, "bootstrap": {"observed": 0.045, "lo": 0.01, "hi": 0.08, "p_noise": 0.03}}
    assert "Evidence is building" in report.verdict(longer)
    noisy = {"n_days": 90, "bootstrap": {"observed": 0.01, "lo": -0.03, "hi": 0.05, "p_noise": 0.4}}
    assert "No evidence of skill" in report.verdict(noisy)


def test_checklist_marks_unmet_rules():
    st = {"n_days": 14, "bootstrap": {"p_noise": 0.04}, "capm": {"alpha_annual": 0.5, "beta": 0.5}, "dd_record": -0.01, "dd_spy": -0.012}
    rules, passed = report.checklist(st, [], 2, [], True, 0.3)
    status = {r[0][:12]: r[2] for r in rules}
    assert status["At least 60 "] is False and status["At least 4 r"] is False
    assert any("random portfolios" in r[0] and not r[2] for r in rules)
    assert passed == sum(1 for r in rules if r[2])
    _, p2 = report.checklist(st, [], 2, ["2026-10-13"], False, -0.2)
    assert p2 < passed                                  # a missing NAV day, an unlogged change and negative net lead each fail


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
