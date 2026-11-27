"""
Offline test for the market & recession risk models (pipeline/market_risk.py) on synthetic history where
an inverted yield curve and widening credit spreads come before recessions and selloffs.
Run:  python -m pytest tests/  (or)  python tests/test_market_risk.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PIPELINE_ROOT"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import market_risk as mr, util  # noqa: E402


def synthetic(stress_now):
    rng = np.random.default_rng(7)
    months = pd.date_range("1960-01-31", "2026-08-31", freq="ME")
    rec = pd.Series(0.0, index=months)
    starts = [pd.Timestamp(x) for x in ("1970-01-31", "1974-01-31", "1980-03-31", "1990-08-31", "2001-04-31"
                                        if False else "2001-04-30", "2008-01-31", "2020-03-31")]
    for s in starts:
        rec[(rec.index >= s) & (rec.index < s + pd.DateOffset(months=10))] = 1
    lead = pd.Series(0.0, index=months)                  # 1 in the 12 months before each recession
    for s in starts:
        lead[(lead.index >= s - pd.DateOffset(months=12)) & (lead.index < s)] = 1
    if stress_now:
        lead.iloc[-8:] = 1
    noise = lambda sd: rng.normal(0, sd, len(months))
    gs10 = pd.Series(5 + noise(0.3), index=months)
    tb3 = gs10 - (1.8 - 2.6 * lead + noise(0.4))
    nfci = pd.Series(-0.4 + 0.9 * lead + noise(0.3), index=months)
    sahm = pd.Series(0.1 + 0.3 * lead + 0.5 * rec + noise(0.05), index=months)
    days = pd.bdate_range("1970-01-01", "2026-09-25")
    lead_d = lead.reindex(days, method="ffill").fillna(0)
    rets = rng.normal(0.0004, 0.009, len(days)) * (1 + 1.5 * lead_d.values) - 0.0012 * lead_d.values
    spx = pd.Series(100 * np.exp(np.cumsum(rets)), index=days)
    weekly = pd.date_range("1967-01-07", "2026-09-19", freq="W-SAT")
    lead_w = lead.reindex(weekly, method="ffill").fillna(0)
    icsa = pd.Series(300000 * (1 + 0.3 * lead_w.rolling(26, min_periods=1).mean()) + rng.normal(0, 8000, len(weekly)), index=weekly)
    nfci_w = nfci.reindex(weekly, method="ffill")
    hy = pd.Series(4 + 3 * lead_d.rolling(60, min_periods=1).mean().values + rng.normal(0, 0.15, len(days)), index=days)
    lead_all = lead.reindex(days, method="ffill").fillna(0)
    stress = lead_all.shift(-40).fillna(lead_all.iloc[-1])         # geopolitical stress shows up ~2 months early
    gprd = pd.Series(np.exp(4.5 + 0.8 * stress.values + rng.normal(0, 0.25, len(days))), index=days)
    epu = pd.Series(np.exp(4.6 + rng.normal(0, 0.3, len(days))), index=days)       # pure noise
    series = {"USEPUINDXD": epu, "EPUTRADE": monthly_noise(months, rng), "OVXCLS": pd.Series(35 + rng.normal(0, 5, len(days)), index=days),
              "GS10": gs10, "TB3MS": tb3, "T10Y3M": (gs10 - tb3).reindex(days, method="ffill").dropna(),
              "NFCI": nfci_w.dropna(), "SAHMREALTIME": sahm, "ICSA": icsa, "USREC": rec,
              "BAMLH0A0HYM2": hy[hy.index >= "2023-09-30"], "BAA10Y": hy[hy.index >= "1986-01-02"], "RECPROUSM156N": rec * 90 + 3}

    def fred_get(sid, start):
        return series[sid][series[sid].index >= start]
    return fred_get, spx, {"GPRD": gprd, "OIL_CURVE": (90.0, 82.0, "CLZ26.NYM")}


def monthly_noise(months, rng):
    return pd.Series(np.exp(4.8 + rng.normal(0, 0.3, len(months))), index=months)


def test_models_find_the_signal_and_report():
    calm = mr.compute(*synthetic(False))
    stressed = mr.compute(*synthetic(True))
    t = stressed["pullback_10pct_3m"]["inputs_tested"]
    assert t["Economic policy uncertainty, 30-day average (log)"]["kept"] is False       # noise isn't kept
    names = {i["name"]: i for i in stressed["indicators"]}
    assert "Geopolitical Risk Index (30-day avg)" in names and "backwardation" in names["Oil futures curve (front vs ~6 months out)"]["reading"]
    assert "Tested input" in "\n".join(mr.report_md(stressed))
    for r in (calm, stressed):
        assert not r.get("error")
        assert r["recession_12m"]["out_of_sample"]["auc"] > 0.8          # inputs really do lead recessions here
        assert r["pullback_10pct_3m"]["out_of_sample"]["auc"] > 0.6
    assert stressed["recession_12m"]["probability"] > 0.5 > calm["recession_12m"]["probability"]
    assert stressed["pullback_10pct_3m"]["probability"] > calm["pullback_10pct_3m"]["probability"]
    top = stressed["recession_12m"]["drivers"][0]
    assert top["push"] > 0                                               # the biggest push raises the risk
    assert stressed["recession_12m"]["benchmarks"]["ny_fed_style_yield_curve_model"] > \
        calm["recession_12m"]["benchmarks"]["ny_fed_style_yield_curve_model"]
    c = mr.calc_entries(stressed)
    assert c["recession_risk"]["level"] == "HIGH" and "Yield curve (10y - 3m)" in c["risk_indicators"]
    assert "Recession within 12 months" in "\n".join(mr.report_md(stressed))
    assert "rose to HIGH" in mr.tripwire(stressed, calm) and mr.tripwire(stressed, stressed) is None
    mr.save(calm)
    mr.save(calm)                                                        # same day twice: one row
    assert len(pd.read_csv(util.state_path("market_risk_history.csv"))) == 1
    # missing data: reported, never raised
    fg, spx, extra = synthetic(False)
    bad = mr.compute(lambda sid, start: (_ for _ in ()).throw(RuntimeError("down")) if sid == "NFCI" else fg(sid, start), spx, extra)
    assert "NFCI" in bad["error"] and mr.calc_entries(bad) == {}


if __name__ == "__main__":
    test_models_find_the_signal_and_report()
    print("PASS test_models_find_the_signal_and_report")
