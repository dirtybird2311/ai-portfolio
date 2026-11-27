"""
STATISTICS  —  pure functions (numpy / pandas only) used by the performance and statistics reports. Nothing here
touches the network, the state folder or the live trading path.

  Returns and risk
    max_drawdown(nav)                    worst peak-to-trough fall, as a fraction (negative)
    active_stats(port, bench)            mean active return, tracking error, information ratio, t-stat
  Is the lead more than noise?
    block_bootstrap(x, ...)              circular block bootstrap of a daily series: range of the cumulative sum
    random_portfolio_test(...)           where the real picks rank among thousands of random portfolios
    capm(port, bench)                    alpha and beta with Newey-West errors
    factor_regression(port, factors)     the same against several factor series (size, value, momentum proxies)
  The signal screen
    two_sided_p(t)                       normal-approximation p-value from a t-stat (fine for 60+ observations)
    benjamini_hochberg(p, q)             false-discovery-rate cut: which signals survive many tests
    deflated_sharpe(...)                 Sharpe ratio after allowing for how many strategies were tried
  Deciding
    sprt(x, mu1, ...)                    Wald sequential test of 'no edge' against 'edge of mu1 a day'
    ledoit_wolf(returns)                 shrunk covariance matrix for short histories
"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

TRADING_DAYS = 252
_N = NormalDist()


# ==================================================================== returns and risk
def max_drawdown(nav):
    s = pd.Series(nav, dtype=float).dropna()
    if s.empty:
        return 0.0
    return float((s / s.cummax() - 1).min())


def active_stats(port, bench):
    """port, bench: aligned daily simple returns. Returns n, mean/day, tracking error/day, annualised IR, t-stat."""
    a = (pd.Series(port, dtype=float) - pd.Series(bench, dtype=float)).dropna()
    n = len(a)
    if n < 3:
        return {"n": n, "mean": float("nan"), "te": float("nan"), "ir": float("nan"), "t": float("nan")}
    sd = float(a.std(ddof=1))
    mean = float(a.mean())
    return {"n": n, "mean": mean, "te": sd, "ir": mean / sd * math.sqrt(TRADING_DAYS) if sd else float("nan"),
            "t": mean / sd * math.sqrt(n) if sd else float("nan")}


# ==================================================================== is the lead more than noise?
def block_bootstrap(x, block=3, n_boot=5000, seed=0, alpha=0.05):
    """Circular block bootstrap of daily values `x` (e.g. daily active return). Resampling runs of `block` days
    keeps the day-to-day dependence that a plain bootstrap throws away. Returns the range of the cumulative sum
    over the same number of days and the share of resamples that end above zero."""
    x = np.asarray(pd.Series(x, dtype=float).dropna())
    n = len(x)
    if n < 4:
        return {"n": n, "lo": float("nan"), "hi": float("nan"), "p_positive": float("nan"), "observed": float(x.sum())}
    block = max(1, min(block, n))
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    sums = x[idx.reshape(n_boot, -1)[:, :n]].sum(axis=1)
    # the bootstrap distribution is centred on the observed sum; ask how often a no-edge world would do as well
    centred = sums - x.sum()
    return {"n": n, "observed": float(x.sum()), "lo": float(np.quantile(sums, alpha / 2)),
            "hi": float(np.quantile(sums, 1 - alpha / 2)),
            "p_positive": float((sums > 0).mean()),
            "p_noise": float((centred >= x.sum()).mean())}


def random_portfolio_test(weights, returns, sectors=None, n=5000, seed=0, match_sectors=True):
    """Where do the real picks rank among random portfolios from the same pool?
    weights  {ticker: weight} of the stock picks (the SPY sleeve left out)
    returns  Series of each pool stock's return over the period (the picks must be in it)
    sectors  optional {ticker: sector}; with match_sectors each random portfolio holds as many names per sector
             as the real one, so the test does not just reward a sector bet
    Each random portfolio gets the real weight vector assigned to randomly drawn names. Returns the actual
    return, the random portfolios' mean / sd / 5th and 95th percentile, and the share of random portfolios the
    real one beat."""
    ret = pd.Series(returns, dtype=float).dropna()
    w = pd.Series({t: float(v) for t, v in weights.items() if t in ret.index and v > 0})
    if len(w) < 2 or len(ret) <= len(w):
        return {"ok": False, "why": "too few picks with prices"}
    w = w / w.sum()
    actual = float((w * ret[w.index]).sum())
    rng = np.random.default_rng(seed)
    wv = w.values
    pool = ret.index.to_numpy()
    sims = np.empty(n)
    groups = None
    if sectors and match_sectors:
        sec = pd.Series({t: sectors.get(t) for t in ret.index}).dropna()
        counts = pd.Series({t: sectors.get(t) for t in w.index}).dropna().value_counts()
        if len(counts) and all((sec == s).sum() >= c for s, c in counts.items()) and len(w) == counts.sum():
            groups = [(sec[sec == s].index.to_numpy(), int(c)) for s, c in counts.items()]
    rv = ret.values
    pos = {t: i for i, t in enumerate(ret.index)}
    for k in range(n):
        if groups:
            names = np.concatenate([rng.choice(g, size=c, replace=False) for g, c in groups])
        else:
            names = rng.choice(pool, size=len(w), replace=False)
        sims[k] = float((rng.permutation(wv) * rv[[pos[t] for t in names]]).sum())
    return {"ok": True, "actual": actual, "random_mean": float(sims.mean()), "random_sd": float(sims.std(ddof=1)),
            "p5": float(np.quantile(sims, 0.05)), "p95": float(np.quantile(sims, 0.95)),
            "beat_share": float((sims < actual).mean() + 0.5 * (sims == actual).mean()),
            "z": float((actual - sims.mean()) / sims.std(ddof=1)) if sims.std(ddof=1) else float("nan"),
            "n_picks": int(len(w)), "pool_size": int(len(ret)), "sector_matched": bool(groups), "n_sims": n}


def _newey_west_cov(X, resid, lag):
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    u = X * resid[:, None]
    S = u.T @ u
    for L in range(1, lag + 1):
        w = 1 - L / (lag + 1)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    return XtX_inv @ S @ XtX_inv


def ols(y, X, lag=None):
    """OLS with an intercept. y: Series; X: DataFrame. Returns coefficients, Newey-West t-stats and R^2."""
    df = pd.concat([pd.Series(y, name="__y"), pd.DataFrame(X)], axis=1).dropna()
    n = len(df)
    names = ["alpha"] + [str(c) for c in df.columns[1:]]
    if n < len(names) + 3:
        return {"n": n, "ok": False}
    Xm = np.column_stack([np.ones(n), df.iloc[:, 1:].values])
    ym = df.iloc[:, 0].values
    beta = np.linalg.lstsq(Xm, ym, rcond=None)[0]
    resid = ym - Xm @ beta
    lag = lag if lag is not None else max(1, int(round(n ** 0.25)))
    se = np.sqrt(np.diag(_newey_west_cov(Xm, resid, min(lag, n - 2))))
    ss_tot = ((ym - ym.mean()) ** 2).sum()
    return {"n": n, "ok": True, "coef": dict(zip(names, map(float, beta))),
            "t": dict(zip(names, map(float, beta / se))), "r2": float(1 - (resid ** 2).sum() / ss_tot) if ss_tot else 0.0}


def capm(port, bench):
    """Daily alpha (and annualised) and beta of `port` on `bench`."""
    r = ols(port, pd.DataFrame({"market": pd.Series(bench, dtype=float)}))
    if not r["ok"]:
        return r
    r["alpha_annual"] = r["coef"]["alpha"] * TRADING_DAYS
    r["beta"] = r["coef"]["market"]
    return r


def factor_regression(port, factors):
    """port: daily returns; factors: DataFrame of daily factor returns (market, size, value, momentum proxies)."""
    r = ols(port, factors)
    if r["ok"]:
        r["alpha_annual"] = r["coef"]["alpha"] * TRADING_DAYS
    return r


# ==================================================================== the signal screen
def two_sided_p(t):
    return 2 * (1 - _N.cdf(abs(float(t))))


def benjamini_hochberg(pvals, q=0.10):
    """pvals {name: p}. Returns {name: (adjusted p, survives)}: the false-discovery-rate cut for many tests."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj, prev = {}, 1.0
    for rank, (name, p) in reversed(list(enumerate(items, start=1))):
        prev = min(prev, p * m / rank)
        adj[name] = prev
    return {k: (adj[k], adj[k] <= q) for k in pvals}


def deflated_sharpe(sr, n_obs, n_trials, skew=0.0, kurt=3.0, sr_sd=None):
    """Probability that the true Sharpe ratio is above zero once the best of `n_trials` tried strategies is
    taken into account (Bailey and Lopez de Prado). `sr` is the per-period Sharpe of the chosen strategy, `sr_sd`
    the spread of Sharpe ratios across the trials (default: the sampling sd of one Sharpe)."""
    if n_obs < 3:
        return float("nan")
    sr_sd = sr_sd if sr_sd is not None else math.sqrt((1 + 0.5 * sr * sr) / (n_obs - 1))
    g = 0.5772156649
    expected_max = sr_sd * ((1 - g) * _N.inv_cdf(1 - 1 / max(n_trials, 2))
                            + g * _N.inv_cdf(1 - 1 / (max(n_trials, 2) * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    return float(_N.cdf((sr - expected_max) * math.sqrt(n_obs - 1) / denom))


# ==================================================================== deciding
def sprt(x, mu1, sd=None, alpha=0.05, beta=0.20):
    """Wald sequential probability ratio test on daily active returns x: H0 mean 0 vs H1 mean mu1 (>0), normal
    with a known or estimated sd. Returns the running log-likelihood ratio and 'edge' / 'no edge' / 'continue'."""
    x = np.asarray(pd.Series(x, dtype=float).dropna())
    n = len(x)
    if n < 3:
        return {"n": n, "llr": 0.0, "decision": "continue"}
    sd = sd or float(x.std(ddof=1))
    llr = float(((mu1 / sd ** 2) * (x - mu1 / 2)).sum()) if sd else 0.0
    upper, lower = math.log((1 - beta) / alpha), math.log(beta / (1 - alpha))
    decision = "edge" if llr >= upper else "no edge" if llr <= lower else "continue"
    return {"n": n, "llr": llr, "upper": upper, "lower": lower, "decision": decision}


def ledoit_wolf(returns):
    """Ledoit-Wolf shrinkage of the sample covariance toward a scaled identity. Returns (matrix, shrinkage)."""
    X = pd.DataFrame(returns).dropna()
    n, p = X.shape
    if n < 3 or p < 2:
        return X.cov(), 0.0
    Xc = X.values - X.values.mean(axis=0)
    S = Xc.T @ Xc / n
    mu = np.trace(S) / p
    d2 = ((S - mu * np.eye(p)) ** 2).sum()
    b2 = sum(((np.outer(x, x) - S) ** 2).sum() for x in Xc) / n ** 2
    b2 = min(b2, d2)
    k = b2 / d2 if d2 else 0.0
    return pd.DataFrame(k * mu * np.eye(p) + (1 - k) * S, index=X.columns, columns=X.columns), float(k)
