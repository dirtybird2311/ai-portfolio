"""
Offline tests for the screen backtest (pipeline/screentest.py) on made-up history.
Run:  python -m pytest tests/  (or)  python tests/test_screentest.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import screentest as st  # noqa: E402


def fake(value_from="2010-01", seed=0):
    """120 months, 3 sectors x 20 stocks. 'value' predicts the next return from `value_from` on; momentum never does."""
    rng = np.random.default_rng(seed)
    rows = []
    for m in pd.period_range("2010-01", "2019-12", freq="M"):
        d = m.end_time.date().isoformat()
        mkt = rng.normal(0.01, 0.03)
        for s in range(3):
            for i in range(20):
                v, mo = rng.normal(), rng.normal()
                resid = (0.03 * v if str(m) >= value_from else 0.0) + rng.normal(0, 0.05)
                rows.append({"date": d, "ticker": f"S{s}T{i}", "sector": f"S{s}", "resid": resid, "fwd": mkt + resid,
                             "value_raw": v, "mom_raw": mo})
    return pd.DataFrame(rows)


def test_backtest_finds_the_signal_that_works_without_looking_ahead():
    df = fake()
    spy = {d: 0.01 for d in df["date"].unique()}
    res, monthly = st.run(df, spy, {}, {"momentum": 0.5, "value": 0.5}, {"momentum": 1.0})
    m = res["mixes"]
    assert res["first_test_month"] == sorted(df["date"].unique())[st.WARMUP_MONTHS] and m["current"]["months"] == 60
    assert m["wf_ridge"]["ic"]["mean"] > m["current"]["ic"]["mean"] > m["prior"]["ic"]["mean"]
    assert m["wf_ridge"]["ic"]["t"] > 3 and abs(m["prior"]["ic"]["t"]) < 3          # noise stays noise
    assert res["weights"]["wf_ridge"].get("value", 0) > 0.8 and res["weights"]["wf_ic"].get("value", 0) > 0.8
    assert res["vs_current"]["wf_ridge"]["ic"]["diff"] > 0 and m["wf_ridge"]["top_vs_universe"]["mean"] > 0
    assert 0 <= m["current"]["turnover"] <= 1 and set(res["periods"]) == {"2015-2019", "2020-2022", "2023-now"}
    assert "Walk-forward ridge" in st.report(res)

    # value only starts working in 2017: weights fitted for 2016 (on data to Nov 2015) must not know that
    late, names = st.add_scores(fake(value_from="2017-01", seed=1))
    wf = st.walk_forward(late, names, st.monthly_ic(late, names), "2015-01-31")
    w16, w19 = wf["2016"]["wf_ic"], wf["2019"]["wf_ic"]
    assert w16["value"] < 0.2 * w19["value"] and w19["value"] > 0


def test_crash_guard_drops_momentum_only_in_bear_months():
    df = fake(seed=2)
    dates = sorted(df["date"].unique())
    bear = {d: True for d in dates[-12:]}
    res, monthly = st.run(df, {}, bear, {"momentum": 0.5, "value": 0.5}, {"momentum": 1.0})
    g, c = monthly["crash_guard"], monthly["current"]
    assert res["bear_months"] == 12
    assert np.allclose(g["ic"].iloc[:-12], c["ic"].iloc[:-12])                     # same outside bear months
    assert g["ic"].iloc[-12:].mean() > c["ic"].iloc[-12:].mean()                   # value alone beats value + noise
    assert monthly["current"]["top_vs_spy"].isna().all()                           # no SPY data given: left empty


def test_red_flags_show_what_flagged_stocks_did_next():
    df = fake(seed=3)
    rng = np.random.default_rng(4)
    df["roic_raw"] = rng.normal(0.1, 0.1, len(df))
    df["resid"] = df["resid"] - 0.04 * (df["roic_raw"] < 0)                 # money-losers lag by 4% a month
    df["fwd"] = df["fwd"] - 0.04 * (df["roic_raw"] < 0)
    df["lowvol_raw"] = rng.normal(size=len(df))                             # pure noise
    a = st.avoid_test(df, {"momentum": 0.5, "value": 0.5}, sorted(df["date"].unique())[st.WARMUP_MONTHS])
    bad, noise = a["flags"]["Negative return on capital"], a["flags"]["Highest volatility"]
    assert bad["all"]["t"] < -5 and bad["first_half"]["t"] < -3 and bad["second_half"]["t"] < -3
    assert bad["portfolio_gain"]["mean"] > 0 and abs(noise["all"]["t"]) < 3 and 0.05 < noise["share"] < 0.2
    assert "Three or more flags at once" in a["flags"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
