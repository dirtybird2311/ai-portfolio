"""
BASE RATES  —  run:  python -m pipeline.history     (weekly workflow; the heavy part only monthly)

The starting probability every judge begins from: "over 2010-today, how often did stocks that
looked like this one beat their EQUAL-WEIGHTED sector over the next 4 weeks?"

Features (point-in-time: each only from the day it was public):
  m  momentum, 12-1 month return, in fifths across the universe
  e  earnings reaction: stock vs its equal-weighted sector over the 3 days around the latest
     earnings 8-K (Item 2.02) in the last 100 days: -1 (< -3%), 0, +1 (> +3%)
  q  quality: gross profit / assets from the latest annual report FILED by then, in fifths

Outputs
  state/base_rates.json        rate per group (all 75 combinations and every coarser grouping),
                               small groups pulled toward the overall rate, full history next to the
                               last 5 years, with a warning where they disagree
  state/current_features.json  today's m / e / q, trading-history length, and the last 8 earnings
                               reactions for every stock in the screen's bench
Raw inputs are cached in cache/ (restored by the GitHub Actions cache, not committed).

Known limits (stated in the report): today's index members only (survivorship bias), Yahoo
prices adjusted for splits/dividends as of today.
"""
import itertools
import pickle
from bisect import bisect_right
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config
from .util import now_et, read_json, state_path, write_json

TODAY = now_et().date()
CACHE = config.ROOT / "cache"
FEATURES = ("m", "e", "q")                  # always in the base-rate table
OPTIONAL_FEATURES = {"v": "value", "l": "low_vol"}   # joined when 15 years of history supports the signal (|t| >= 2)
FEATURE_T_MIN = 2.0
REACTION_BAND = 0.03
EVENT_MAX_AGE = 100          # days an earnings reaction stays "current"


# ==================================================================== equal-weighted sector benchmark
def ew_sector_index(px, sector_of, min_names=3):
    """Daily equal-weighted index per sector (each stock's daily return counts equally)."""
    ret = px.pct_change(fill_method=None)
    cols = [c for c in ret.columns if sector_of.get(c)]
    groups = pd.Series({c: sector_of[c] for c in cols})
    out = {}
    for s, names in groups.groupby(groups).groups.items():
        r = ret[list(names)]
        m = r.mean(axis=1).where(r.notna().sum(axis=1) >= min_names)
        out[s] = (1 + m.fillna(0)).cumprod()
    return pd.DataFrame(out, index=px.index)


def window(series, i, j):
    if i < 0 or j >= len(series):
        return np.nan
    a, b = series.iloc[i], series.iloc[j]
    return float(b / a - 1) if pd.notna(a) and pd.notna(b) and a > 0 else np.nan


# ==================================================================== features
def quintile(s):
    s = s.dropna()
    if len(s) < 10:
        return pd.Series(dtype=float)
    return pd.Series(np.ceil(s.rank(pct=True) * 5).clip(1, 5), index=s.index)


def momentum_at(px, i):
    if i < 252:
        return pd.Series(dtype=float)
    a, b = px.iloc[i - 252], px.iloc[i - 21]
    return (b / a - 1).replace([np.inf, -np.inf], np.nan)


def event_reactions(px, ew, sector_of, edates):
    """{ticker: [(date, reaction)]}: stock minus equal-weighted sector, close before -> 2 days after."""
    out = {}
    idx = px.index
    for t, dates in edates.items():
        if t not in px or not sector_of.get(t) or sector_of[t] not in ew:
            continue
        rows = []
        for d in dates:
            k = idx.searchsorted(pd.Timestamp(d))
            r = window(px[t], k - 1, k + 2) - window(ew[sector_of[t]], k - 1, k + 2)
            if r == r:
                rows.append((d, round(r, 4)))
        out[t] = rows
    return out


def level(r):
    if r is None or r != r:
        return np.nan
    return -1 if r < -REACTION_BAND else (1 if r > REACTION_BAND else 0)


def reaction_at(reactions, t, d):
    rows = reactions.get(t) or []
    k = bisect_right([x[0] for x in rows], d)
    if not k:
        return np.nan
    ed, r = rows[k - 1]
    return r if (date.fromisoformat(d) - date.fromisoformat(ed)).days <= EVENT_MAX_AGE else np.nan


def quality_at(qhist, t, d):
    rows = qhist.get(t) or []
    k = bisect_right([x[0] for x in rows], d)
    return rows[k - 1][1] if k else np.nan


def fund_at(fhist, t, d):
    rows = fhist.get(t) or []
    k = bisect_right([x[0] for x in rows], d)
    return rows[k - 1][1] if k else {}


def risk_at(px, i):
    """Blended volatility, risk-adjusted and residual momentum at day i (vectorized over all stocks)."""
    if i < 252:
        return pd.DataFrame()
    r = px.iloc[i - 251:i + 1].pct_change(fill_method=None).iloc[1:]
    m = r.mean(axis=1)
    v252 = r.std() * np.sqrt(252)
    v60 = r.tail(60).std() * np.sqrt(252)
    blend = np.sqrt(0.5 * v60 ** 2 + 0.5 * v252 ** 2)
    rc, mc = r - r.mean(), m - m.mean()
    beta = rc.mul(mc, axis=0).sum() / (mc ** 2).sum()
    resid = r - np.outer(m.values, beta.values)
    win = resid.iloc[:-21]
    sd = resid.std()
    mom = momentum_at(px, i)
    rw = r.iloc[:-21]
    pos, neg = (rw > 0).mean(), (rw < 0).mean()
    return pd.DataFrame({"vol_blend": blend, "mom_riskadj": mom / v252.replace(0, np.nan),
                         "mom_resid": win.sum() / (sd * np.sqrt(len(win))).replace(0, np.nan),
                         "info_discrete": np.sign(mom) * (neg - pos)})


def frog(mom, info_discrete):
    """"Frog in the pan" momentum (Da, Gurun & Warachka 2014): momentum counted more when it came from many
    small moves (low information discreteness, -1..1) than from a few jumps. Higher = better."""
    return (mom.rank(pct=True) - 0.5) * (1 - info_discrete)


def features_at(px, i, reactions, qhist, sub_of=None, fhist=None, alt=None):
    """Base-rate features (quintiles/levels) plus the raw signals the screen's weights are tested on."""
    d = px.index[i].date().isoformat()
    tick = [t for t in px.columns if pd.notna(px[t].iloc[i])]
    mom = momentum_at(px, i).reindex(tick)
    react = pd.Series({t: reaction_at(reactions, t, d) for t in tick}, dtype=float)
    qual = pd.Series({t: quality_at(qhist, t, d) for t in tick}, dtype=float)
    out = pd.DataFrame({"m": quintile(mom).reindex(tick), "e": react.map(level), "q": quintile(qual).reindex(tick),
                        "mom_raw": mom, "react_raw": react, "qual_raw": qual})
    out["rev_1m"] = (px.iloc[i] / px.iloc[max(0, i - 21)] - 1).reindex(tick) if i >= 21 else np.nan
    if sub_of:
        sub = pd.Series({t: sub_of.get(t) for t in tick})
        out["ind_mom"] = mom.groupby(sub).transform("mean")
    rk = risk_at(px, i)
    if len(rk):
        out["resid_raw"] = rk["mom_resid"].reindex(tick)
        out["riskadj_raw"] = rk["mom_riskadj"].reindex(tick)
        out["lowvol_raw"] = -rk["vol_blend"].reindex(tick)
        out["fip_raw"] = frog(mom, rk["info_discrete"].reindex(tick))
    if "lowvol_raw" in out:
        out["l"] = quintile(out["lowvol_raw"]).reindex(tick)      # 5 = calmest
    if fhist:
        price = px.iloc[i]
        f = {t: fund_at(fhist, t, d) for t in tick}
        mcap = pd.Series({t: (price[t] * f[t]["shares"]) if f[t].get("shares") else np.nan for t in tick})
        oi = pd.Series({t: f[t].get("op_income", np.nan) for t in tick}, dtype=float)
        fcf = pd.Series({t: f[t].get("fcf") if f[t].get("fcf") is not None else np.nan for t in tick}, dtype=float)
        out["value_raw"] = pd.concat([(oi / mcap).rank(pct=True), (fcf / mcap).rank(pct=True)], axis=1).mean(axis=1)
        out["roic_raw"] = pd.Series({t: f[t].get("roic") if f[t].get("roic") is not None else np.nan for t in tick}, dtype=float)
        out["stab_raw"] = pd.Series({t: f[t].get("margin_stability") if f[t].get("margin_stability") is not None else np.nan
                                     for t in tick}, dtype=float)
        out["v"] = quintile(out["value_raw"]).reindex(tick)        # 5 = cheapest
        num = lambda k, sign=1: pd.Series({t: sign * f[t][k] if f[t].get(k) is not None else np.nan for t in tick}, dtype=float)
        out["issuance_raw"] = num("share_growth", -1)                # buybacks score high
        out["assetg_raw"] = num("asset_growth", -1)                  # slow asset growth scores high
        out["fscore_raw"] = num("fscore")
    if i >= 251:
        out["high52_raw"] = (px.iloc[i] / px.iloc[i - 251:i + 1].max()).reindex(tick)   # 1 = at its 52-week high
    if alt:
        from .altdata import lazy_at, norm_symbol, short_at
        if alt.get("short"):
            si = short_at(alt["short"], d)
            if si:
                out["short_raw"] = pd.Series({t: -si[norm_symbol(t)] if norm_symbol(t) in si else np.nan for t in tick},
                                             dtype=float)                 # fewer days to cover scores high
        if alt.get("lazy"):
            out["lazy_raw"] = pd.Series({t: lazy_at(alt["lazy"], t, d) for t in tick}, dtype=float)
    return out


# ==================================================================== history -> samples -> table
EXTRA_RAW = ("resid_raw", "riskadj_raw", "lowvol_raw", "value_raw", "roic_raw", "stab_raw",
             "issuance_raw", "assetg_raw", "fscore_raw", "high52_raw", "fip_raw", "short_raw", "lazy_raw")


def samples(px, sector_of, reactions, qhist, start, horizon=20, sub_of=None, fhist=None, alt=None):
    """One row per (month-end, stock): features then, and whether it beat its equal-weighted
    sector over the next `horizon` trading days (clock starts the day after, like the grader)."""
    ew = ew_sector_index(px, sector_of)
    month_ends = px.index.to_series().groupby(px.index.to_period("M")).max()
    rows = []
    for ts in month_ends[month_ends >= pd.Timestamp(start)]:
        i = px.index.get_loc(ts)
        j0, j1 = i + 1, i + 1 + horizon
        if j1 >= len(px.index):
            break
        f = features_at(px, i, reactions, qhist, sub_of, fhist, alt)
        for t, row in f.iterrows():
            s = sector_of.get(t)
            if not s or s not in ew:
                continue
            r, b = window(px[t], j0, j1), window(ew[s], j0, j1)
            if r == r and b == b:
                rows.append({"date": ts.date().isoformat(), "ticker": t, "sector": s, "m": row.m, "e": row.e, "q": row.q,
                             "beat": int(r > b), "resid": r - b, "mom_raw": row.mom_raw, "react_raw": row.react_raw,
                             "qual_raw": row.qual_raw, "rev_1m": row.rev_1m, "ind_mom": row.get("ind_mom", np.nan),
                             **{k: row.get(k, np.nan) for k in EXTRA_RAW + tuple(OPTIONAL_FEATURES)}})
    return pd.DataFrame(rows)


# signal name in the screen -> (column in the samples, sign)
SIGNALS = {"momentum": ("mom_raw", 1), "reaction": ("react_raw", 1), "quality": ("qual_raw", 1),
           "industry": ("ind_mom", 1), "reversal": ("rev_1m", -1),
           # tested from point-in-time filings and prices (value was untested before)
           "value": ("value_raw", 1), "resid_momentum": ("resid_raw", 1), "riskadj_momentum": ("riskadj_raw", 1),
           "low_vol": ("lowvol_raw", 1), "roic": ("roic_raw", 1), "stability": ("stab_raw", 1),
           "net_issuance": ("issuance_raw", 1), "asset_growth": ("assetg_raw", 1), "fscore": ("fscore_raw", 1),
           "high_52w": ("high52_raw", 1), "frog_momentum": ("fip_raw", 1), "low_short": ("short_raw", 1),
           "filing_similarity": ("lazy_raw", 1)}


def signal_evidence(df, min_names=20, skip=()):
    """How well each screen signal predicted the next 4 weeks' return vs the equal-weighted sector,
    2010-now: mean monthly rank correlation (IC) within sectors, with its t-stat."""
    out = {}
    for name, (col, sign) in SIGNALS.items():
        if col not in df or name in skip:
            continue
        ics = []
        for _, g in df.dropna(subset=[col, "resid"]).groupby("date"):
            if len(g) < min_names:
                continue
            by = [x for _, x in g.groupby("sector") if len(x) >= 5]
            vals = [sign * x[col].rank().corr(x.resid.rank()) for x in by]
            vals = [v for v in vals if v == v]
            if vals:
                ics.append(float(np.mean(vals)))
        if len(ics) > 2:
            m, sd = float(np.mean(ics)), float(np.std(ics, ddof=1))
            out[name] = {"mean_ic": round(m, 4), "t": round(m / (sd / np.sqrt(len(ics))), 2) if sd > 0 else None,
                         "months": len(ics)}
    # "tested" = attempted; a signal whose data isn't ready yet (skip) is left out so it's tested once it is
    return {"built": TODAY.isoformat(), "signals": out, "tested": sorted(set(SIGNALS) - set(skip))}


def key_of(feats):
    return "|".join(f"{k}={int(feats[k])}" for k in sorted(feats))


def table_features(evidence):
    """Base-rate features: momentum, earnings reaction and quality always; value and volatility only
    when their 15-year evidence is strong (|t| >= 2)."""
    sig = (evidence or {}).get("signals", {})
    extra = [k for k, name in OPTIONAL_FEATURES.items() if abs((sig.get(name) or {}).get("t") or 0) >= FEATURE_T_MIN]
    return tuple(FEATURES) + tuple(extra)


def build_table(df, cfg=None, features=FEATURES):
    cfg = cfg or config.BASE_RATE
    K, rec_years, warn = cfg["shrink"], cfg["recent_years"], cfg["recent_gap_warn"]
    overall = float(df.beat.mean())
    last = pd.Timestamp(df.date.max())
    recent_mask = pd.to_datetime(df.date) >= last - pd.DateOffset(years=rec_years)
    rec_overall = float(df[recent_mask].beat.mean()) if recent_mask.any() else overall
    groups = {}
    features = tuple(f for f in features if f in df)
    df = df[["date", *features, "beat"]]
    for n in range(0, len(features) + 1):
        for subset in itertools.combinations(features, n):
            sub = df.dropna(subset=list(subset)) if subset else df
            if not subset:
                grouped = [((), sub)]
            else:
                grouped = sub.groupby(list(subset))
            for vals, g in grouped:
                vals = vals if isinstance(vals, tuple) else (vals,)
                feats = dict(zip(subset, vals))
                gr = g[recent_mask.reindex(g.index, fill_value=False)]
                n_all, hits = len(g), int(g.beat.sum())
                rate = (hits + K * overall) / (n_all + K)
                r_rate = (int(gr.beat.sum()) + K * rec_overall) / (len(gr) + K) if len(gr) else None
                groups[key_of(feats) if feats else "all"] = {
                    "n": n_all, "raw_%": round(hits / n_all * 100, 1) if n_all else None,
                    "p": round(rate, 4), "recent_p": round(r_rate, 4) if r_rate is not None else None,
                    "recent_n": len(gr),
                    "warn": bool(r_rate is not None and len(gr) >= cfg["min_group"] and abs(r_rate - rate) * 100 >= warn)}
    return {"built": TODAY.isoformat(), "samples": len(df), "first": df.date.min(), "last": df.date.max(),
            "overall": round(overall, 4), "recent_overall": round(rec_overall, 4), "groups": groups,
            "features": list(features),
            "horizon_days": cfg["horizon_days"], "benchmark": "equal-weighted sector",
            "caveats": ["today's index members only (survivorship bias)", "prices adjusted as of today"]}


def lookup(table, feats, min_group=None):
    """Starting probability for a stock. Missing features (or thin groups) fall back to coarser groups,
    dropping quality first, then earnings reaction, then momentum."""
    min_group = min_group or config.BASE_RATE["min_group"]
    if not table:
        return {"p": 0.5, "n": 0, "group": "none (no base-rate table yet)", "recent_p": None, "warn": False}
    use = table.get("features") or FEATURES
    have = {k: v for k, v in (feats or {}).items() if k in use and v is not None and v == v}
    order = [k for k in ("l", "v", "q", "e", "m") if k in have]
    tried = [have]
    for k in order:
        tried.append({x: v for x, v in tried[-1].items() if x != k})
    for f in tried:
        key = key_of(f) if f else "all"
        g = table["groups"].get(key)
        if g and (g["n"] >= min_group or not f):
            return {"p": g["p"], "n": g["n"], "group": key, "recent_p": g.get("recent_p"), "warn": g.get("warn", False)}
    return {"p": table["overall"], "n": table["samples"], "group": "all", "recent_p": None, "warn": False}


def describe(b):
    """One dossier line for the judges."""
    names = {"m": "momentum", "e": "earnings reaction", "q": "quality", "v": "value", "l": "calmness (low volatility)"}
    grp = "; ".join(f"{names.get(k, k)} {v}" for k, v in (x.split("=") for x in b["group"].split("|"))) \
        if "=" in str(b.get("group")) else b.get("group")
    txt = (f"Base rate: {b['p'] * 100:.1f}% of similar stocks ({grp}; groups 1-5, 5 = highest; {b['n']:,} past cases, "
           f"2010-now) beat their equal-weighted sector over the next 4 weeks. It already reflects: "
           f"{', '.join(names[k.split('=')[0]] for k in str(b.get('group')).split('|') if k.split('=')[0] in names) or 'nothing specific'}.")
    if b.get("recent_p") is not None:
        txt += f" Last 5 years: {b['recent_p'] * 100:.1f}%."
    if b.get("warn"):
        txt += " WARNING: the recent rate differs from the long history; weigh which applies now."
    return txt


# ==================================================================== data gathering (network)
FUNDAMENTALS_HIST_FIELDS = ("share_growth", "asset_growth", "fscore")   # cached entries without these are re-read


def _cache(name, default):
    p = CACHE / name
    if not p.exists():
        return default
    with p.open("rb") as f:
        return pickle.load(f)


def _save(name, obj):
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / name).open("wb") as f:
        pickle.dump(obj, f)


def download_prices(tickers, start):
    import yfinance as yf
    data = yf.download([t.replace(".", "-") for t in tickers], start=start, progress=False, auto_adjust=True,
                       threads=True)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    data.columns = [c.replace("-", ".") for c in data.columns]
    return data.sort_index()


def refresh_events_and_quality(sec, bench, full):
    """Earnings dates and quality history per ticker, cached. full=True: everything (first build);
    otherwise only companies that filed something since last time (from the screen's SEC walk)."""
    from .sec import fundamental_history, quality_history, revenue_history
    ed = _cache("earnings_dates.pkl", {})
    qh = _cache("quality.pkl", {})
    fh = _cache("fundamentals_hist.pkl", {})
    old = lambda t: bool(fh.get(t)) and not all(k in fh[t][-1][1] for k in FUNDAMENTALS_HIST_FIELDS)
    n_old = sum(old(t) for t in fh)
    if n_old:        # new fields: re-read those companies' filings once (resumes if a run times out)
        print(f"    point-in-time fundamentals gained fields: re-reading filings for {n_old} companies (once)")
    rv = _cache("revenue.pkl", {})
    st = read_json(state_path("sec_state.json"), {}) or {}
    recent = set(st.get("filers_since_history", []))
    rows = bench.dropna(subset=["cik"])
    n = 0
    for r in rows.itertuples():
        cik = int(r.cik)
        if not full and r.ticker in ed and r.ticker in fh and cik not in recent and not old(r.ticker):
            continue
        if full or r.ticker not in ed or cik in recent:
            ed[r.ticker] = sec.earnings_dates(cik, config.BASE_RATE["start"], full=full or r.ticker not in ed)
        if full or r.ticker not in qh or r.ticker not in fh or cik in recent or old(r.ticker):
            cf = sec.companyfacts(cik)
            qh[r.ticker], rv[r.ticker], fh[r.ticker] = quality_history(cf), revenue_history(cf), fundamental_history(cf)
        n += 1
        if n % 100 == 0:          # save as we go: a run that times out resumes where it stopped
            _save("earnings_dates.pkl", ed)
            _save("quality.pkl", qh)
            _save("revenue.pkl", rv)
            _save("fundamentals_hist.pkl", fh)
            print(f"      {n} companies")
    _save("earnings_dates.pkl", ed)
    _save("quality.pkl", qh)
    _save("revenue.pkl", rv)
    _save("fundamentals_hist.pkl", fh)
    st["filers_since_history"] = []
    write_json(state_path("sec_state.json"), st)
    return ed, qh, n


def valuation_history(price, shares, revs, years=5):
    """Price-to-sales now and its percentile vs the last `years` (month-ends), using each year's revenue
    from the day it was filed. Uses today's share count throughout (ignores buybacks/dilution)."""
    if not shares or not revs or price is None or not len(price):
        return None, None
    s = price.dropna()
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=years)].resample("ME").last().dropna()
    filed = [r[0] for r in revs]
    vals = []
    for ts, px_ in s.items():
        k = bisect_right(filed, ts.date().isoformat())
        if k and revs[k - 1][1]:
            vals.append(px_ * shares / revs[k - 1][1])
    if len(vals) < 12:
        return (round(vals[-1], 2) if vals else None), None
    now = vals[-1]
    return round(now, 2), round(float(np.mean([v <= now for v in vals]) * 100))


def revenue_growth(revs, n=4):
    """Last n annual revenue growth rates (%), oldest first."""
    v = [r[1] for r in sorted(revs or [], key=lambda r: r[2])]
    g = [round((b / a - 1) * 100, 1) for a, b in zip(v[:-1], v[1:]) if a and a > 0]
    return g[-n:]


def current(px, sector_of, reactions, qhist, tickers, revs=None, shares=None, fhist=None):
    """Today's features for the bench, plus history length, recent earnings reactions, valuation vs
    its own history, and revenue growth."""
    revs, shares = revs or {}, shares or {}
    i = len(px.index) - 1
    f = features_at(px, i, reactions, qhist, fhist=fhist)
    out = {}
    today = px.index[i].date().isoformat()
    for t in tickers:
        if t not in px:
            continue
        s = px[t].dropna()
        first = s.index[0].date() if len(s) else None
        row = f.loc[t] if t in f.index else None
        out[t] = {"m": None if row is None or row.m != row.m else int(row.m),
                  "e": None if row is None or row.e != row.e else int(row.e),
                  "q": None if row is None or row.q != row.q else int(row.q),
                  **{k: (None if row is None or k not in row or row[k] != row[k] else int(row[k])) for k in OPTIONAL_FEATURES},
                  "first_price": first.isoformat() if first else None,
                  "history_days": (TODAY - first).days if first else 0,
                  "reactions": [{"date": d, "vs_sector_%": round(r * 100, 1)} for d, r in (reactions.get(t) or [])[-8:]],
                  "reaction_now_%": (None if reaction_at(reactions, t, today) != reaction_at(reactions, t, today)
                                     else round(reaction_at(reactions, t, today) * 100, 2))}
        ps, pct = valuation_history(px[t], shares.get(t), revs.get(t))
        out[t].update({"ps_now": ps, "ps_pct_5y": pct, "rev_growth_%": revenue_growth(revs.get(t))})
    return out


def alt_data(sec, bench, get=None):
    """Short-interest history (FINRA, cached) and 10-K similarities (advanced ~40 minutes per run).
    Returns (alt, signals to skip because their data isn't complete yet)."""
    from . import altdata
    si = _cache("short_interest.pkl", {})
    try:
        n = altdata.refresh_short_history(si, **({"get": get} if get else {}))
        _save("short_interest.pkl", si)
        print(f"    FINRA short interest: {len(si.get('files', {}))} files cached ({n} new)")
    except Exception as e:
        print(f"    ! FINRA short interest: {str(e)[:100]}")
    lazy = {}
    try:
        st = altdata.update_lazy(sec, [(r.ticker, int(r.cik)) for r in bench.dropna(subset=["cik"]).itertuples()])
        lazy = altdata.lazy_history(st)
    except Exception as e:
        print(f"    ! 10-K similarity: {str(e)[:100]}")
    skip = set() if lazy else {"filing_similarity"}
    if not si.get("files"):
        skip.add("low_short")
    return {"short": si, "lazy": lazy}, skip


def main(session=None, folder=None, sec=None, force=False):
    from .sec import SEC
    bp = state_path("bench.csv")
    if not bp.exists():
        print("No bench yet (the screen hasn't run): nothing to do.")
        return {"status": "no bench"}
    bench = pd.read_csv(bp)
    sector_of = dict(zip(bench.ticker, bench.sector))
    sub_of = dict(zip(bench.ticker, bench.sub_industry)) if "sub_industry" in bench else None
    tickers = list(bench.ticker)
    table = read_json(state_path("base_rates.json"))
    stale = force or not table or (TODAY - date.fromisoformat(table["built"])).days >= config.BASE_RATE["rebuild_days"]
    sec = sec or SEC()
    alt, skip = alt_data(sec, bench)
    tested = (read_json(state_path("signal_evidence.json")) or {}).get("tested", [])
    if set(SIGNALS) - set(skip) - set(tested) or (table and "features" not in table):
        stale = True                        # new signals to test: rebuild the evidence now, not in a month
    full = not (CACHE / "earnings_dates.pkl").exists()
    print(f"1/3 Earnings dates and quality history ({'full backfill: slow, once' if full else 'recent filers only'})...")
    edates, qhist, n = refresh_events_and_quality(sec, bench, full)
    print(f"    updated {n} companies")
    print("2/3 Prices...")
    if stale:
        px = download_prices(tickers, "2009-01-01")
        _save("prices.pkl", px)
    else:
        px = _cache("prices.pkl", None)
        recent = download_prices(tickers, (TODAY - timedelta(days=460)).isoformat())
        px = recent if px is None else pd.concat([px[px.index < recent.index[0]], recent]).sort_index()
        px = px.loc[:, ~px.columns.duplicated()]
        _save("prices.pkl", px)
    ew = ew_sector_index(px, sector_of)
    reactions = event_reactions(px, ew, sector_of, edates)
    if stale:
        print("3/3 Rebuilding the base-rate table from history...")
        df = samples(px, sector_of, reactions, qhist, config.BASE_RATE["start"], config.BASE_RATE["horizon_days"], sub_of,
                     _cache("fundamentals_hist.pkl", {}), alt)
        ev = signal_evidence(df, skip=skip)
        table = build_table(df, features=table_features(ev))
        write_json(state_path("base_rates.json"), table)
        write_json(state_path("signal_evidence.json"), ev)
        print(f"    base-rate features: {', '.join(table['features'])}")
        print(f"    {table['samples']:,} cases; overall {table['overall'] * 100:.1f}% beat their sector")
    else:
        print("3/3 Base-rate table is fresh; updating today's features only")
    fc = read_json(state_path("fundamentals_cache.json"), {}) or {}
    shares = {r.ticker: (fc.get(str(int(r.cik))) or {}).get("shares") for r in bench.dropna(subset=["cik"]).itertuples()}
    feats = current(px, sector_of, reactions, qhist, tickers, _cache("revenue.pkl", {}), shares,
                    _cache("fundamentals_hist.pkl", {}))
    write_json(state_path("current_features.json"), {"date": TODAY.isoformat(), "stocks": feats})
    return {"status": "rebuilt" if stale else "features"}


if __name__ == "__main__":
    import sys
    from .runner import run_stage
    run_stage("history", lambda s, f: main(s, f, force="--force" in sys.argv))
