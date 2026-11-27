"""
Offline tests for pipeline/stats.py (synthetic data with known answers). Run: python -m pytest tests/  (or)  python tests/test_stats.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline import stats  # noqa: E402


def test_max_drawdown():
    assert abs(stats.max_drawdown([100, 120, 90, 110]) - (-0.25)) < 1e-12
    assert stats.max_drawdown([100, 101, 102]) == 0.0


def test_active_stats_and_ir():
    rng = np.random.default_rng(1)
    b = pd.Series(rng.normal(0, 0.01, 400))
    p = b + 0.002 + rng.normal(0, 0.004, 400)
    a = stats.active_stats(p, b)
    assert a["n"] == 400 and abs(a["mean"] - 0.002) < 0.0007 and a["t"] > 8 and a["ir"] > 5


def test_block_bootstrap_sees_noise_and_edge():
    rng = np.random.default_rng(2)
    noise = pd.Series(rng.normal(0, 0.01, 60))
    r = stats.block_bootstrap(noise, block=3, n_boot=3000)
    assert r["lo"] < 0 < r["hi"] and 0.02 < r["p_noise"] < 0.98
    edge = pd.Series(rng.normal(0.01, 0.005, 60))
    e = stats.block_bootstrap(edge, block=3, n_boot=3000)
    assert e["lo"] > 0 and e["p_noise"] < 0.01
    # runs matter: strongly autocorrelated days give a wider range than treating days as independent
    ar = np.zeros(200)
    for i in range(1, 200):
        ar[i] = 0.8 * ar[i - 1] + rng.normal(0, 0.01)
    w1 = stats.block_bootstrap(ar, block=1, n_boot=3000)
    w10 = stats.block_bootstrap(ar, block=10, n_boot=3000)
    assert (w10["hi"] - w10["lo"]) > (w1["hi"] - w1["lo"])


def test_random_portfolio_test_ranks_best_and_typical():
    rng = np.random.default_rng(3)
    tick = [f"S{i}" for i in range(300)]
    ret = pd.Series(rng.normal(0.02, 0.08, 300), index=tick)
    best = ret.nlargest(8).index
    r = stats.random_portfolio_test({t: 1.0 for t in best}, ret, n=2000)
    assert r["ok"] and r["beat_share"] > 0.999 and r["z"] > 3
    typical = list(ret.sample(8, random_state=5).index)
    r2 = stats.random_portfolio_test({t: 1.0 for t in typical}, ret, n=3000, seed=1)
    assert 0.02 < r2["beat_share"] < 0.98
    secs = {t: ["A", "B", "C"][i % 3] for i, t in enumerate(tick)}
    picks = {"S0": 1, "S3": 1, "S1": 1, "S4": 1, "S2": 1}
    r3 = stats.random_portfolio_test(picks, ret, sectors=secs, n=500)
    assert r3["sector_matched"] and r3["n_picks"] == 5
    assert stats.random_portfolio_test({"S0": 1}, ret)["ok"] is False


def test_capm_and_factor_regression_recover_betas():
    rng = np.random.default_rng(4)
    n = 500
    f = pd.DataFrame({"market": rng.normal(0, 0.01, n), "size": rng.normal(0, 0.005, n), "value": rng.normal(0, 0.005, n)})
    y = 0.0004 + 1.2 * f["market"] + 0.5 * f["value"] + rng.normal(0, 0.002, n)
    c = stats.capm(y, f["market"])
    assert abs(c["beta"] - 1.2) < 0.2
    r = stats.factor_regression(y, f)
    assert abs(r["coef"]["market"] - 1.2) < 0.05 and abs(r["coef"]["value"] - 0.5) < 0.1 and abs(r["coef"]["size"]) < 0.1
    assert abs(r["coef"]["alpha"] - 0.0004) < 0.0004 and r["r2"] > 0.9


def test_fdr_and_deflated_sharpe():
    p = {"a": 0.001, "b": 0.012, "c": 0.04, "d": 0.30, "e": 0.80}
    out = stats.benjamini_hochberg(p, q=0.10)
    assert out["a"][1] and out["b"][1] and not out["d"][1] and not out["e"][1]
    assert abs(stats.two_sided_p(1.96) - 0.05) < 0.001
    one = stats.deflated_sharpe(0.15, 250, 1)
    many = stats.deflated_sharpe(0.15, 250, 100)
    assert many < one and 0 <= many <= 1


def test_sprt_and_ledoit_wolf():
    rng = np.random.default_rng(5)
    assert stats.sprt(rng.normal(0.01, 0.01, 200), mu1=0.01)["decision"] == "edge"
    assert stats.sprt(rng.normal(0.0, 0.01, 400), mu1=0.01)["decision"] == "no edge"
    assert stats.sprt(rng.normal(0.003, 0.01, 4), mu1=0.01)["decision"] == "continue"
    X = pd.DataFrame(rng.normal(0, 0.01, (40, 30)))
    cov, k = stats.ledoit_wolf(X)
    assert 0 < k < 1 and np.linalg.cond(cov.values) < np.linalg.cond(X.cov().values)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
