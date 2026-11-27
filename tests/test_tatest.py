"""
Offline tests for the technical-indicator backtest (pipeline/tatest.py) on made-up prices.
Run:  python -m pytest tests/  (or)  python tests/test_tatest.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import tatest  # noqa: E402


def test_indicators_use_only_past_prices_and_read_the_right_way():
    days = pd.bdate_range("2020-01-01", periods=400)
    up = pd.Series(np.linspace(50, 150, 400), index=days)            # steady climb
    down = pd.Series(np.linspace(150, 50, 400), index=days)          # steady fall
    px = pd.DataFrame({"UP": up, "DOWN": down})
    d = days[350]
    pan = tatest.panels(px, [d.date().isoformat()])
    one = lambda n: pan[n].loc[d]
    assert one("above_200dma")["UP"] > 0 > one("above_200dma")["DOWN"] and one("golden_cross")["UP"] > 0 > one("golden_cross")["DOWN"]
    assert one("new_high_3m")["UP"] and one("new_low_3m")["DOWN"] and not one("new_high_3m")["DOWN"]
    assert one("rsi_oversold")["DOWN"] > one("rsi_oversold")["UP"] and one("rsi_under_30")["DOWN"] and one("rsi_over_70")["UP"]
    assert one("near_support")["DOWN"] > one("near_support")["UP"] and one("roc_3m")["UP"] > 0 > one("roc_3m")["DOWN"]
    assert one("above_200dma_flag")["UP"] and not one("above_200dma_flag")["DOWN"]
    # nothing after the sample date can change a value: scramble the future and recompute
    px2 = px.copy()
    px2.iloc[351:] = px2.iloc[351:] * 3
    pan2 = tatest.panels(px2, [d.date().isoformat()])
    for n in pan:
        a, b = pan[n].loc[d], pan2[n].loc[d]
        assert ((a == b) | (a.isna() & b.isna())).all(), n


def test_run_reports_alone_patterns_and_together():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2009-01-01", "2019-12-31")
    tick = [f"S{s}T{i}" for s in range(3) for i in range(20)]
    drift = pd.Series(rng.normal(0, 0.0008, len(tick)), index=tick)          # persistent winners and losers: trend works
    px = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(days), len(tick))) + drift.to_numpy(), axis=0)),
                      index=days, columns=tick)
    rows = []
    for m in pd.period_range("2010-01", "2019-10", freq="M"):
        i = px.index.get_indexer([px.index[px.index <= m.end_time][-1]])[0]
        fwd = px.iloc[i + 21] / px.iloc[i + 1] - 1
        for t in tick:
            sec = t[:2]
            rows.append({"date": px.index[i].date().isoformat(), "ticker": t, "sector": sec, "fwd": fwd[t],
                         "resid": fwd[t] - fwd[[x for x in tick if x[:2] == sec]].mean(), "value_raw": rng.normal(), "mom_raw": rng.normal()})
    df = pd.DataFrame(rows)
    res = tatest.run(df, px, {}, {"value": 0.5, "momentum": 0.5})
    assert set(res["alone"]) == set(tatest.INDICATORS) and set(res["patterns"]) == set(tatest.PATTERNS)
    assert res["alone"]["roc_6m"]["ic"]["t"] > 3 and res["alone"]["near_support"]["ic"]["t"] < -2     # trend works, dip-buying fails
    assert set(res["together"]) == {"current", "ta_equal", "ta_wf_ic", "ta_ridge", "current_plus_ta"}
    assert res["together"]["ta_ridge"]["ic"]["mean"] > res["together"]["current"]["ic"]["mean"]       # current = two noise signals
    assert res["vs_current"]["current_plus_ta"]["ic"]["diff"] > 0 and 0 < res["patterns"]["above_200dma_flag"]["share"] < 1
    so = res["screen_out"]
    assert len(so) == 2 * len(tatest.INDICATORS) + len(tatest.PATTERNS)
    worst = so["Up over the last 6 months: the LEAST so (bottom tenth)"]                              # persistent losers
    assert worst["dropped"]["t"] < -3 and worst["first_half"]["t"] < 0 and worst["second_half"]["t"] < 0 and 0.05 < worst["share"] < 0.15
    md = tatest.report(res)
    assert "As a screen-out rule" in md
    assert "Each indicator alone" in md and "Together" in md
    out = Path(tempfile.mkdtemp()) / "t.png"
    tatest.chart(res, out)
    assert out.stat().st_size > 5000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
