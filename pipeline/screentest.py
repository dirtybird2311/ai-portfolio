"""
SCREEN BACKTEST  —  run:  python -m pipeline.screentest      (Actions > Screen backtest; needs the history cache)

Does the screen's mix of signals pick better stocks on history it was not fitted to, and would a different mix
do better? Analysis only: it changes no weight, pick or setting.

Data: the same point-in-time samples the base rates use (pipeline.history.samples): one row per month-end and
stock since 2010, each signal as it was known that day, and the stock's return over the next 20 trading days
against its equal-weighted sector. Signals are ranked 0-1 inside the sector, missing = 0.5, as in the screen.

Mixes compared, all on the same out-of-sample months (after a 60-month warm-up):
  current        today's screen weights, the testable signals only (earnings estimates and insider buying have
                 no history here, so about a quarter of the live weight is left out of every mix)
  prior          the starting weights before any history adjustment
  equal          one equal vote per family (momentum, quality) and stand-alone signal
  wf_ic          walk-forward: each year, weights in proportion to each signal's past rank correlation, shrunk
                 for short or noisy histories; signals with a negative past record get nothing
  wf_ridge       walk-forward ridge regression on all signals, penalty chosen by leave-one-year-out on the
                 past only, negative weights cut to zero
  halfway        halfway between current and wf_ridge (the shrink-toward-what-we-have option)
  crash_guard    current, with the momentum family switched off while the equal-weighted market's last 12
                 months are negative (momentum's crashes come in rebounds after bear markets)

"Walk-forward" means the weights used in a year were fitted only on months that had fully played out before it.

Measures per mix: the monthly rank correlation with the next 4 weeks (IC) and its t-stat; what a sector-balanced
portfolio of the top 2 names per sector earned against the equal-weighted universe and against SPY; how much of
that portfolio changes each month; three sub-periods; and a paired test against the current mix.

Known limits, the same as the base rates: today's index members only (survivorship bias flatters every mix about
equally), Yahoo's adjusted prices, month-end rebalancing, no trading costs (turnover is reported so they can be
judged). Outputs: reports/screentest/latest.md, chart.png, state/screentest.json.
"""
import sys

import numpy as np
import pandas as pd

from . import config, history
from .util import now_et, state_path, write_json, write_text

WARMUP_MONTHS = 60
TOP_PER_SECTOR = 2
RIDGE_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)       # penalty as a multiple of the average signal variance
RETURN_CAP = 0.5                                 # portfolio results count a 4-week move of at most +/-50%: one GameStop
                                                 # (+1,600% in January 2021) otherwise decides a whole mix's result
COST_PER_TRADE = 0.001                           # 10 basis points each way, for the after-cost column
IC_SHRINK_MONTHS = 60                            # a signal with this much history counts half
PERIODS = (("2015-2019", "2015-01-01", "2019-12-31"), ("2020-2022", "2020-01-01", "2022-12-31"),
           ("2023-now", "2023-01-01", "2099-12-31"))
MOMENTUM = ("momentum", "industry", "resid_momentum", "riskadj_momentum", "high_52w", "frog_momentum")
QUALITY = ("quality", "roic", "stability", "fscore")


# ==================================================================== scores
def add_scores(df, signals=None):
    """s_<signal>: rank 0-1 inside the date's sector (higher = better by the signal's own sign), missing = 0.5.
    y: the same rank of the next-4-weeks return vs the sector. signals: {name: (column, sign)}, default the screen's."""
    df = df.copy()
    g = df.groupby(["date", "sector"])
    names = []
    for name, (col, sign) in (signals or history.SIGNALS).items():
        if col in df and df[col].notna().any():
            df[f"s_{name}"] = (sign * df[col]).groupby([df["date"], df["sector"]]).rank(pct=True).fillna(0.5)
            names.append(name)
    df["y"] = g["resid"].rank(pct=True)
    return df, names


def composite(df, weights):
    tot = sum(w for w in weights.values() if w > 0)
    if tot <= 0:
        return pd.Series(0.5, index=df.index)
    return sum(w * df[f"s_{k}"] for k, w in weights.items() if w > 0 and f"s_{k}" in df) / tot


def by_family(weights):
    out = {}
    for k, w in weights.items():
        fam = "momentum" if k in MOMENTUM else "quality" if k in QUALITY else k
        out[fam] = out.get(fam, 0.0) + w
    tot = sum(out.values()) or 1.0
    return {k: round(v / tot, 3) for k, v in sorted(out.items(), key=lambda kv: -kv[1]) if v > 0}


# ==================================================================== walk-forward weights
def monthly_ic(df, names):
    """IC of each signal per month: mean over sectors of the rank correlation with the next 4 weeks."""
    rows = {}
    for d, g in df.groupby("date"):
        r = {}
        for k in names:
            vals = [x[f"s_{k}"].corr(x["y"]) for _, x in g.groupby("sector") if len(x) >= 5 and x[f"s_{k}"].nunique() > 1]
            vals = [v for v in vals if v == v]
            r[k] = float(np.mean(vals)) if vals else np.nan
        rows[d] = r
    return pd.DataFrame(rows).T.sort_index()


def ic_weights(ics_past):
    """Weights from past monthly ICs: mean IC, shrunk for short histories and by its own noise, never negative."""
    w = {}
    for k in ics_past.columns:
        s = ics_past[k].dropna()
        if len(s) < 24:
            w[k] = 0.0
            continue
        m, se = s.mean(), s.std(ddof=1) / np.sqrt(len(s))
        t = m / se if se > 0 else 0.0
        w[k] = max(0.0, m) * len(s) / (len(s) + IC_SHRINK_MONTHS) * min(1.0, abs(t) / 2.0)
    return w


def _moments(g, cols):
    x = g[cols].to_numpy() - 0.5
    y = g["y"].to_numpy() - 0.5
    ok = ~np.isnan(y)
    x, y = x[ok], y[ok]
    return x.T @ x, x.T @ y, len(y)


def ridge_fit(xtx, xty, n, lam):
    k = len(xty)
    scale = np.trace(xtx) / k if k else 1.0
    return np.linalg.solve(xtx + lam * scale * np.eye(k), xty)


def ridge_weights(mom, cols):
    """Ridge on the past months' moments {date: (X'X, X'y, n)}; the penalty is the one whose leave-one-year-out
    forecasts (each year predicted from the other past years) had the best mean monthly correlation."""
    dates = sorted(mom)
    years = sorted({d[:4] for d in dates})
    tot = [sum(mom[d][i] for d in dates) for i in range(2)]
    best, best_lam = -9.0, RIDGE_GRID[-1]
    if len(years) >= 3:
        for lam in RIDGE_GRID:
            score = []
            for y in years:
                held = [d for d in dates if d[:4] == y]
                a = tot[0] - sum(mom[d][0] for d in held)
                b = tot[1] - sum(mom[d][1] for d in held)
                beta = ridge_fit(a, b, 0, lam)
                # fit quality on the held-out year from its moments: beta'X'y / sqrt(beta'X'X beta)
                for d in held:
                    den = float(beta @ mom[d][0] @ beta)
                    if den > 0:
                        score.append(float(beta @ mom[d][1]) / np.sqrt(den))
            if score and np.mean(score) > best:
                best, best_lam = float(np.mean(score)), lam
    beta = ridge_fit(tot[0], tot[1], 0, best_lam)
    return {c[2:]: max(0.0, float(b)) for c, b in zip(cols, beta)}, best_lam


def walk_forward(df, names, ics, start):
    """{year: {"wf_ic": weights, "wf_ridge": weights, "lambda": penalty}} for every test year, each fitted on
    months whose 4-week outcome was known before that year began."""
    cols = [f"s_{k}" for k in names]
    mom = {d: _moments(g, cols) for d, g in df.groupby("date")}
    out = {}
    for year in sorted({d[:4] for d in mom if d >= start}):
        past = [d for d in sorted(mom) if d < f"{int(year) - 1}-12-01"]     # the December sample ends in January: left out
        if len(past) < 24:
            continue
        rw, lam = ridge_weights({d: mom[d] for d in past}, cols)
        out[year] = {"wf_ic": ic_weights(ics.loc[[d for d in ics.index if d in set(past)]]), "wf_ridge": rw, "lambda": lam}
    return out


# ==================================================================== evaluation
def evaluate(df, comp, spy):
    """Monthly results of one mix: IC, and the top-2-per-sector portfolio's return vs the equal-weighted universe
    and vs SPY, with its turnover."""
    d = df.assign(c=comp)
    rows, prev = [], None
    for date, g in d.groupby("date"):
        ics = [x["c"].corr(x["y"]) for _, x in g.groupby("sector") if len(x) >= 5 and x["c"].nunique() > 1]
        ics = [v for v in ics if v == v]
        h = g.dropna(subset=["fwd"])
        h = h.assign(fwd=h["fwd"].clip(-RETURN_CAP, RETURN_CAP), resid=h["resid"].clip(-RETURN_CAP, RETURN_CAP))
        top = h.sort_values("c", ascending=False).groupby("sector").head(TOP_PER_SECTOR)
        names = set(top["ticker"])
        rows.append({"date": date, "ic": float(np.mean(ics)) if ics else np.nan,
                     "top_sector_excess": float(top["resid"].mean()),
                     "top_vs_universe": float(top["fwd"].mean() - h["fwd"].mean()),
                     "top_vs_spy": float(top["fwd"].mean() - spy.get(date, np.nan)),
                     "turnover": (1 - len(names & prev) / len(names)) if prev and names else np.nan})
        prev = names
    return pd.DataFrame(rows).set_index("date")


def summary(m):
    def stat(s, annual=True):
        s = s.dropna()
        if len(s) < 3:
            return {"mean": None, "t": None}
        se = s.std(ddof=1) / np.sqrt(len(s))
        return {"mean": round(float(s.mean() * (12 if annual else 1)), 4), "t": round(float(s.mean() / se), 2) if se > 0 else None,
                "lo": round(float((s.mean() - 1.96 * se) * (12 if annual else 1)), 4),
                "hi": round(float((s.mean() + 1.96 * se) * (12 if annual else 1)), 4)}
    return {"months": int(m["ic"].notna().sum()), "ic": stat(m["ic"], annual=False),
            "top_sector_excess": stat(m["top_sector_excess"]), "top_vs_universe": stat(m["top_vs_universe"]),
            "top_vs_spy": stat(m["top_vs_spy"]), "turnover": round(float(m["turnover"].mean()), 3),
            "net_vs_universe": round(float(m["top_vs_universe"].mean() * 12 - m["turnover"].mean() * 12 * 2 * COST_PER_TRADE), 4)
            if m["top_vs_universe"].notna().sum() > 2 and m["turnover"].notna().any() else None,
            "beat_spy_months": round(float((m["top_vs_spy"].dropna() > 0).mean()), 3)}


def paired(a, b, col="ic"):
    d = (a[col] - b[col]).dropna()
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 2 else 0
    return {"diff": round(float(d.mean()), 4), "t": round(float(d.mean() / se), 2) if se > 0 else None}


def run(df, spy, bear, current_w, prior_w):
    """All mixes on df (samples with fwd). spy: {date: SPY's next-4-weeks return}; bear: {date: bool}."""
    df, names = add_scores(df)
    months = sorted(df["date"].unique())
    if len(months) <= WARMUP_MONTHS + 12:
        raise SystemExit(f"only {len(months)} months of samples: need more than {WARMUP_MONTHS + 12}")
    start = months[WARMUP_MONTHS]
    ics = monthly_ic(df, names)
    wf = walk_forward(df, names, ics, start)
    test = df[df["date"] >= start].copy()
    cur = {k: v for k, v in current_w.items() if k in names and v > 0}
    pri = {k: v for k, v in prior_w.items() if k in names and v > 0}
    fams = {}
    for k in cur:
        fams.setdefault("momentum" if k in MOMENTUM else "quality" if k in QUALITY else k, []).append(k)
    equal = {k: 1.0 / len(fams) / len(ms) for ms in fams.values() for k in ms}

    def yearly(key, blend=None):
        s = pd.Series(np.nan, index=test.index)
        for y, w in wf.items():
            idx = test.index[test["date"].str[:4] == y]
            ww = dict(w[key])
            if blend:
                tot_c, tot_w = sum(cur.values()) or 1, sum(ww.values()) or 1
                ww = {k: 0.5 * cur.get(k, 0) / tot_c + 0.5 * ww.get(k, 0) / tot_w for k in set(cur) | set(ww)}
            s.loc[idx] = composite(test.loc[idx], ww)
        return s

    guard = pd.Series(np.nan, index=test.index)
    for flag, w in ((False, cur), (True, {k: v for k, v in cur.items() if k not in MOMENTUM})):
        idx = test.index[test["date"].map(lambda x: bool(bear.get(x, False))) == flag]
        guard.loc[idx] = composite(test.loc[idx], w)
    mixes = {"current": composite(test, cur), "prior": composite(test, pri), "equal": composite(test, equal),
             "wf_ic": yearly("wf_ic"), "wf_ridge": yearly("wf_ridge"), "halfway": yearly("wf_ridge", blend=True),
             "crash_guard": guard}
    monthly = {k: evaluate(test, v, spy) for k, v in mixes.items()}
    res = {"built": now_et().date().isoformat(), "first_test_month": start, "last_test_month": months[-1],
           "capped_moves": int((test["fwd"].abs() > RETURN_CAP).sum()), "samples": int(len(test)),
           "signals": names, "untested_live_weight": round(sum(v for k, v in current_w.items() if k not in names), 3),
           "bear_months": int(sum(bool(bear.get(m)) for m in months if m >= start)), "market_now": bear.get("now"),
           "weights": {"current": by_family(cur), "prior": by_family(pri), "equal": by_family(equal),
                       **{k: by_family(wf[max(wf)][k]) for k in ("wf_ic", "wf_ridge")}},
           "latest_ridge_weights": {k: round(v, 4) for k, v in sorted(wf[max(wf)]["wf_ridge"].items(), key=lambda kv: -kv[1]) if v > 0},
           "ridge_penalty_by_year": {y: w["lambda"] for y, w in wf.items()},
           "mixes": {k: summary(m) for k, m in monthly.items()},
           "vs_current": {k: {"ic": paired(m, monthly["current"]), "top_vs_spy": paired(m, monthly["current"], "top_vs_spy")}
                          for k, m in monthly.items() if k != "current"},
           "periods": {p: {k: summary(m.loc[(m.index >= a) & (m.index <= b)]) for k, m in monthly.items()}
                       for p, a, b in PERIODS},
           "signal_ic": {k: {"mean": round(float(ics.loc[ics.index >= start, k].mean()), 4),
                             "t": round(float(ics.loc[ics.index >= start, k].mean()
                                              / (ics.loc[ics.index >= start, k].std(ddof=1) / np.sqrt(ics.loc[ics.index >= start, k].notna().sum()))), 2)}
                         for k in names if ics.loc[ics.index >= start, k].notna().sum() > 12}}
    return res, monthly


# ==================================================================== red flags: what to screen OUT
# Each flag is fixed in advance (worst tenth inside the sector, or a plain threshold): nothing is fitted.
# (column, sign that makes HIGH good, rule) ; rule "decile" = the worst 10% inside the sector that month
FLAGS = {
    "Highest volatility": ("lowvol_raw", 1, "decile"),
    "Biggest 12-month losers": ("mom_raw", 1, "decile"),
    "Furthest below 52-week high": ("high52_raw", 1, "decile"),
    "Biggest 1-month jump": ("rev_1m", -1, "decile"),
    "Missed earnings (fell over 3% on the report)": ("react_raw", 1, ("below", -history.REACTION_BAND)),
    "Most expensive": ("value_raw", 1, "decile"),
    "Lowest profitability": ("qual_raw", 1, "decile"),
    "Negative return on capital": ("roic_raw", 1, ("below", 0.0)),
    "Least stable margins": ("stab_raw", 1, "decile"),
    "Weak financial health (F-score 3 or less)": ("fscore_raw", 1, ("below", 3.5)),
    "Most share issuance": ("issuance_raw", 1, "decile"),
    "Fastest asset growth": ("assetg_raw", 1, "decile"),
    "Most heavily shorted": ("short_raw", 1, "decile"),
    "Most-changed annual report": ("lazy_raw", 1, "decile"),
}


def flag_columns(df):
    out = {}
    for name, (col, sign, rule) in FLAGS.items():
        if col not in df or not df[col].notna().any():
            continue
        if rule == "decile":
            rk = (sign * df[col]).groupby([df["date"], df["sector"]]).rank(pct=True)
            out[name] = (rk <= 0.10) & df[col].notna()
        else:
            out[name] = (sign * df[col] < rule[1]) & df[col].notna()
    return pd.DataFrame(out, index=df.index)


def avoid_test(df, current_w, start):
    """For each red flag: what flagged stocks earned against their sector over the next 4 weeks (capped moves),
    in the first and second half of the history separately, and what leaving them out does to the current mix's
    top-2-per-sector portfolio. A flag worth using is clearly negative in BOTH halves."""
    df, names = add_scores(df)
    flags = flag_columns(df)
    r = df["resid"].clip(-RETURN_CAP, RETURN_CAP)
    months = sorted(df["date"].unique())
    mid = months[len(months) // 2]
    out = {}

    def stat(mask, dates):
        m = r[mask & df["date"].isin(dates)].groupby(df["date"]).mean().dropna()
        if len(m) < 12:
            return {"mean": None, "t": None, "months": int(len(m))}
        se = m.std(ddof=1) / np.sqrt(len(m))
        return {"mean": round(float(m.mean() * 12), 4), "t": round(float(m.mean() / se), 2) if se > 0 else None, "months": int(len(m))}

    first, second = {d for d in months if d < mid}, {d for d in months if d >= mid}
    flags["Three or more flags at once"] = flags.sum(axis=1) >= 3
    cur = {k: v for k, v in current_w.items() if k in names and v > 0}
    test = df[df["date"] >= start]
    comp = composite(test, cur)
    base = _top_excess(test, comp, None)
    for name in flags:
        f = flags[name]
        ex = _top_excess(test, comp, f.reindex(test.index))
        d = (ex - base).dropna()
        se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 2 else 0
        out[name] = {"share": round(float(f.mean()), 3), "all": stat(f, set(months)), "first_half": stat(f, first),
                     "second_half": stat(f, second),
                     "portfolio_gain": {"mean": round(float(d.mean() * 12), 4), "t": round(float(d.mean() / se), 2) if se > 0 else None}}
    return {"split_at": mid, "flags": out}


def _top_excess(test, comp, drop):
    """Monthly excess over the equal-weighted universe of the top-2-per-sector portfolio, optionally never
    buying flagged names."""
    d = test.assign(c=comp, bad=False if drop is None else drop.fillna(False).to_numpy())
    d = d.dropna(subset=["fwd"])
    d = d.assign(fwd=d["fwd"].clip(-RETURN_CAP, RETURN_CAP))
    uni = d.groupby("date")["fwd"].mean()
    top = d[~d["bad"]].sort_values("c", ascending=False).groupby(["date", "sector"]).head(TOP_PER_SECTOR)
    return top.groupby("date")["fwd"].mean() - uni


# ==================================================================== inputs (the history cache)
def load():
    bp = state_path("bench.csv")
    px = history._cache("prices.pkl", None)
    if px is None or not bp.exists():
        raise SystemExit("No history cache here: this runs in GitHub Actions after the weekly job has built it.")
    bench = pd.read_csv(bp)
    sector_of = dict(zip(bench.ticker, bench.sector))
    sub_of = dict(zip(bench.ticker, bench.sub_industry)) if "sub_industry" in bench else None
    ed, qh, fh = (history._cache(n, {}) for n in ("earnings_dates.pkl", "quality.pkl", "fundamentals_hist.pkl"))
    alt = {"short": history._cache("short_interest.pkl", {}), "lazy": {}}
    try:
        from . import altdata
        alt["lazy"] = altdata.lazy_history()
    except Exception as e:
        print(f"    ! 10-K similarity history unavailable ({str(e)[:80]})")
    ew = history.ew_sector_index(px, sector_of)
    reactions = history.event_reactions(px, ew, sector_of, ed)
    h = config.BASE_RATE["horizon_days"]
    print(f"    building samples from {px.shape[1]} stocks, {px.index[0].date()} to {px.index[-1].date()}...")
    df = history.samples(px, sector_of, reactions, qh, config.BASE_RATE["start"], h, sub_of, fh, alt)
    # raw next-4-weeks return per sample, the market's state, and SPY over the same windows
    pos = {ts.date().isoformat(): i for i, ts in enumerate(px.index)}
    fwd, bear = {}, {}
    mkt = (1 + px.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    for d in df["date"].unique():
        i = pos[d]
        fwd[d] = (px.iloc[i + 1 + h] / px.iloc[i + 1] - 1)
        bear[d] = bool(i >= 252 and mkt.iloc[i] / mkt.iloc[i - 252] - 1 < 0)
    bear["now"] = {"date": px.index[-1].date().isoformat(), "market_12m": round(float(mkt.iloc[-1] / mkt.iloc[-253] - 1), 4)}
    df["fwd"] = [fwd[d].get(t, np.nan) for d, t in zip(df["date"], df["ticker"])]
    spy = {}
    try:
        s = history.download_prices(["SPY"], "2009-01-01")["SPY"].reindex(px.index).ffill()
        spy = {d: float(s.iloc[pos[d] + 1 + h] / s.iloc[pos[d] + 1] - 1) for d in df["date"].unique()}
    except Exception as e:
        print(f"    ! SPY history unavailable ({str(e)[:80]}): the SPY column will be empty")
    load.extra = {"reactions": reactions, "sub_of": sub_of,
                  "cik_of": dict(zip(bench.ticker, bench.cik)) if "cik" in bench else {}}
    return df, spy, bear, px


# ==================================================================== report
LABEL = {"current": "Current weights", "prior": "Starting weights", "equal": "Equal per family",
         "wf_ic": "Walk-forward, by past IC", "wf_ridge": "Walk-forward ridge", "halfway": "Halfway: current + ridge",
         "crash_guard": "Current + momentum crash guard"}


def pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def report(res):
    L = [f"# Screen backtest ({res['built']})", "",
         f"Out-of-sample months: {res['first_test_month']} to {res['last_test_month']} "
         f"({res['mixes']['current']['months']} months). Signals tested: {len(res['signals'])}. "
         f"About {res['untested_live_weight'] * 100:.0f}% of the live screen's weight (earnings estimates, insider buying) "
         f"has no history here and is left out of every mix.", "",
         "## Mixes compared", "",
         "| Mix | IC | t | Top-2-per-sector vs equal-weight universe, a year | 95% range | t | After costs | vs SPY, a year | Months ahead of SPY | Monthly turnover |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in res["mixes"].items():
        L.append(f"| {LABEL[k]} | {s['ic']['mean']:+.4f} | {s['ic']['t']} | {pct(s['top_vs_universe']['mean'])} | "
                 f"{pct(s['top_vs_universe'].get('lo'))} to {pct(s['top_vs_universe'].get('hi'))} | {s['top_vs_universe']['t']} | "
                 f"{pct(s.get('net_vs_universe'))} | {pct(s['top_vs_spy']['mean'])} (t {s['top_vs_spy']['t']}) | "
                 f"{s['beat_spy_months'] * 100:.0f}% | {s['turnover'] * 100:.0f}% |")
    L += ["", "IC = monthly rank correlation between the mix's score and the next 4 weeks' return inside each sector. "
              "A t above about 2 means the result is unlikely to be luck. Portfolio results count a single 4-week move "
              f"of at most +/-{RETURN_CAP * 100:.0f}% ({res['capped_moves']} of {res['samples']:,} stock-months were larger). "
              f"After costs = minus {COST_PER_TRADE * 1e4:.0f} basis points for each buy and sell the monthly turnover implies. "
              "Read the equal-weight-universe columns first: the SPY column is flattered by survivorship (see Limits).", "",
          "## Is any mix better than the current one?", "", "| Mix | IC difference | t | vs-SPY difference, a month | t |", "|---|---|---|---|---|"]
    for k, v in res["vs_current"].items():
        L.append(f"| {LABEL[k]} | {v['ic']['diff']:+.4f} | {v['ic']['t']} | {pct(v['top_vs_spy']['diff'], 2)} | {v['top_vs_spy']['t']} |")
    L += ["", "## By period (top-2-per-sector portfolio vs SPY, a year; IC in brackets)", "",
          "| Mix | " + " | ".join(res["periods"]) + " |", "|---|" + "---|" * len(res["periods"])]
    for k in res["mixes"]:
        L.append(f"| {LABEL[k]} | " + " | ".join(
            f"{pct(res['periods'][p][k]['top_vs_spy']['mean'])} ({res['periods'][p][k]['ic']['mean']:+.3f})"
            if res['periods'][p][k]['ic']['mean'] is not None else "n/a" for p in res["periods"]) + " |")
    L += ["", "## Weights by family", "", "| Mix | Weights |", "|---|---|"]
    for k, w in res["weights"].items():
        L.append(f"| {LABEL[k]} | " + ", ".join(f"{a} {b * 100:.0f}%" for a, b in w.items()) + " |")
    now = res.get("market_now")
    L += ["", f"The momentum crash guard was on in {res['bear_months']} of the test months."
              + (f" Today it would be {'ON' if now['market_12m'] < 0 else 'off'}: the equal-weighted market's last 12 months "
                 f"are {now['market_12m'] * 100:+.1f}% (to {now['date']})." if now else ""), "",
          "## Each signal on its own, same months", "", "| Signal | IC | t |", "|---|---|---|"]
    for k, v in sorted(res["signal_ic"].items(), key=lambda kv: -(kv[1]["t"] or 0)):
        L.append(f"| {k} | {v['mean']:+.4f} | {v['t']} |")
    if res.get("avoid"):
        a = res["avoid"]
        L += ["", "## Red flags: what flagged stocks did next", "",
              f"Each flag marks stocks at month-end; the figure is what they earned against their sector over the next 4 "
              f"weeks, a year. A flag worth screening on is clearly negative in both halves of the history (split at "
              f"{a['split_at']}). With {len(a['flags'])} flags tried, a t below about -2.9 is the bar for one of them alone.", "",
              "| Flag | Share of stocks | All years | t | First half | t | Second half | t | Effect on the portfolio if never bought | t |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in sorted(a["flags"].items(), key=lambda kv: (kv[1]["all"]["t"] is None, kv[1]["all"]["t"] or 0)):
            L.append(f"| {k} | {v['share'] * 100:.0f}% | {pct(v['all']['mean'])} | {v['all']['t']} | {pct(v['first_half']['mean'])} | "
                     f"{v['first_half']['t']} | {pct(v['second_half']['mean'])} | {v['second_half']['t']} | "
                     f"{pct(v['portfolio_gain']['mean'], 2)} | {v['portfolio_gain']['t']} |")
    L += ["", "## Limits", "",
          "- Today's index members only: companies that failed or were dropped are missing, which flatters every mix.",
          "- No trading costs. At 10 basis points a trade, a portfolio that replaces X% of its names each month loses "
          "about X% x 12 x 0.2% a year.",
          "- The portfolio here is 2 names per sector, equal weight, rebuilt monthly: a stand-in, not the live rules.",
          "- The SPY column is not a fair fight. The universe is today's S&P 1500 members carried back in time, so it "
          "already holds the small companies that went on to grow; that puts the equal-weighted universe ahead of SPY "
          "in this test, where real equal-weighted funds lagged it. The equal-weight-universe column removes most of "
          "the effect and is the one to trust."]
    return "\n".join(L) + "\n"


def chart(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = list(res["mixes"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, col, title in ((axes[0], "top_vs_universe", "vs the equal-weighted universe"),
                           (axes[1], "top_vs_spy", "vs SPY (flattered)")):
        vals = [res["mixes"][k][col] for k in keys]
        y = range(len(keys))
        for i, (k, v) in enumerate(zip(keys, vals)):
            if v["mean"] is None:
                continue
            c = "#2a78d6" if k == "current" else "#6b6b66"
            ax.plot([v["lo"] * 100, v["hi"] * 100], [i, i], color=c, lw=2, alpha=0.5)
            ax.plot(v["mean"] * 100, i, "o", color=c, ms=8)
            ax.annotate(f"{v['mean'] * 100:+.1f}%", (v["hi"] * 100, i), xytext=(6, -4), textcoords="offset points", fontsize=9)
        ax.axvline(0, color="#999", lw=1)
        ax.set_yticks(list(y))
        ax.set_yticklabels([LABEL[k] for k in keys])
        ax.set_title(f"Top 2 per sector {title}\n(% a year, with 95% range)", fontsize=10, loc="left")
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].invert_yaxis()                     # the y axis is shared: flip it once, current weights on the first row
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main(session=None, folder=None):
    from .screen import PRIOR_WEIGHTS, screen_weights
    print("Screen backtest (analysis only; nothing live changes)")
    df, spy, bear, px = load()
    current_w, _ = screen_weights()
    res, _ = run(df, spy, bear, current_w, PRIOR_WEIGHTS)
    res["avoid"] = avoid_test(df, current_w, res["first_test_month"])
    out = config.ROOT / "reports" / "screentest"
    out.mkdir(parents=True, exist_ok=True)
    write_json(state_path("screentest.json"), res)
    md = report(res)
    write_text(out / "latest.md", md)
    write_text(out / f"screentest-{res['built']}.md", md)
    try:
        chart(res, out / "chart.png")
    except Exception as e:
        print(f"    ! chart not drawn ({str(e)[:80]})")
    print(md[:2500])
    try:                                       # technical indicators: its own report, never blocks the one above
        from . import tatest
        print("Technical-indicator backtest...")
        ta = tatest.run(df, px, spy, current_w)
        write_json(state_path("tatest.json"), ta)
        tmd = tatest.report(ta)
        write_text(out / "technical.md", tmd)
        tatest.chart(ta, out / "technical.png")
        print(tmd[:3000])
    except Exception as e:
        print(f"    ! technical-indicator backtest failed ({type(e).__name__}: {str(e)[:200]})")
    try:                                       # holding period, peer read-across, insider buying
        from . import edgetest
        from .sec import SEC
        print("Edge tests...")
        x = getattr(load, "extra", {})
        ciks = {int(c) for c in x.get("cik_of", {}).values() if c == c}
        buys = None
        try:
            buys = edgetest.insider_history(ciks, SEC().headers)
        except Exception as e:
            print(f"    ! insider data failed ({type(e).__name__}: {str(e)[:150]})")
        ed = edgetest.run(df, px, current_w, res["first_test_month"], x.get("reactions", {}), x.get("sub_of"), buys, x.get("cik_of"))
        write_json(state_path("edgetest.json"), ed)
        emd = edgetest.report(ed)
        write_text(out / "edges.md", emd)
        print(emd[:5000])
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"    ! edge tests failed ({type(e).__name__}: {str(e)[:200]})")
    return {"status": "OK"}


if __name__ == "__main__":
    sys.exit(0 if main().get("status") == "OK" else 1)
