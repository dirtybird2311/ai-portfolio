"""
WEEKLY QUANT SCREEN  —  run:  python -m pipeline.screen   (after the macro agent)

Plain code, no AI, nearly free. Turns the S&P 1500 into a ranked bench and ~90 candidates.

 1. Universe      S&P 500 + 400 + 600 members (Wikipedia lists), GICS sector and sub-industry
 2. Filters       price > $5, enough daily dollar volume
 3. Signals       each ranked 0-1 WITHIN its sector (banks vs banks, REITs vs REITs); starting weights:
                    momentum 25%   12-month return skipping the latest month, plus 3-month
                    earnings 20%   recent earnings surprises (Finnhub) + estimate revisions (Yahoo)
                    reaction 10%   move vs the sector around the latest earnings (post-earnings drift)
                    industry 10%   the sub-industry's own momentum
                    quality  15%   SEC filings: profitability, cash backing earnings, debt
                    value    10%   SEC filings + price: cash-flow / operating-earnings yields
                    insider   5%   open-market buys by insiders, last 90 days (SEC Form 4)
                    reversal  5%   last month's big jump is mildly penalized (short-term reversal)
                  missing data scores neutral (0.5), never a penalty or a bonus. Once a year the
                  weights move halfway toward what 15 years of history says each signal is worth
                  (pipeline.history); a signal that adds nothing is flagged for removal.
 4. Filters       no new candidates with under 12 months of trading, or in distress (high debt +
                  cash burn + operating losses)
 5. Slots         ~90 candidates split across sectors by the macro tilts; at most max(4, 35% of the
                  sector's slots) per sub-industry (standouts in the top 5% and holdings exempt);
                  names the cap keeps out are tracked against the ones that replaced them
    Flags         earnings date inside the holding window, possible acquisition
 6. Output        state/bench.csv, state/candidates.json (incl. screen-only control portfolio),
                  runs/<date>/screen/report.md

SEC data is cached; each week only companies with new filings are re-read.
"""
import io
import json
import math
import os
import re
import time
from datetime import timedelta

import numpy as np
import pandas as pd
import requests

from . import config
from .runner import run_stage
from .sec import SEC
from .util import now_et, read_json, state_path, write_json

TODAY = now_et().date()
UA = {"User-Agent": "Mozilla/5.0 (personal research)"}
WIKI = {"S&P 500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "S&P 400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "S&P 600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"}
GICS_TO_SECTOR = {"Information Technology": "Technology"}   # all other GICS names match config.SECTORS
# Starting weights, tilted toward growth (research: momentum, revisions and quality drive returns; value
# diversifies). Once a year they're re-set halfway toward what history says each signal is worth
# (state/signal_evidence.json from pipeline.history); signals without 5 years of history keep these.
PRIOR_WEIGHTS = {"momentum": 0.22, "industry": 0.08,            # momentum family: 30%
                 "earnings": 0.22, "quality": 0.20, "value": 0.15,
                 "reaction": 0.06, "insider": 0.05, "reversal": 0.02,
                 # CANDIDATE signals: start at zero weight and earn one only if history clears their bar (below)
                 "resid_momentum": 0.0,     # 12-1 month return after removing the market's pull, per unit of risk
                 "riskadj_momentum": 0.0,   # 12-1 month return / 1-year volatility
                 "high_52w": 0.0,           # price vs its 52-week high (near the high keeps rising)
                 "frog_momentum": 0.0,      # momentum built from many small moves, not a few jumps
                 "low_vol": 0.0,            # calmer stocks (blended 60-day / 1-year volatility, lower = better)
                 "roic": 0.0,               # return on invested capital
                 "stability": 0.0,          # steady operating margins over 5 years
                 "fscore": 0.0,             # Piotroski F-score: 9 checks of improving financial health
                 "net_issuance": 0.0,       # buying back shares (vs issuing them) over the last year
                 "asset_growth": 0.0,       # slow balance-sheet growth (fast growers / big acquirers lag)
                 "low_short": 0.0,          # few days to cover short positions (FINRA; heavily shorted lag)
                 "filing_similarity": 0.0}  # "Lazy Prices": 10-K wording barely changed from last year
# Overlapping signals share one budget: a new variant can only take weight from its own family, so adding
# momentum or quality variants never adds more momentum or quality in total.
FAMILIES = {"momentum": ("momentum", "industry", "resid_momentum", "riskadj_momentum", "high_52w", "frog_momentum"),
            "quality": ("quality", "roic", "stability", "fscore")}
CANDIDATE_T_MIN = 1.5                     # t-stat a candidate needs before it earns any weight
CANDIDATE_T_MIN_NEW = {k: 2.0 for k in ("high_52w", "fscore", "net_issuance", "asset_growth", "frog_momentum",
                                         "low_short", "filing_similarity")}      # stricter bar for the newest
WEIGHT_RULE = 2                           # bump when the rule or starting weights change: weights are re-set
WEIGHTS = dict(PRIOR_WEIGHTS)
MOMENTUM_GUARD = True                     # momentum family switched off while the equal-weighted market's last 12 months
                                          # are negative (added Nov 10: the screen backtest's one mix that beat the current
                                          # weights out of sample, 2015-2026; momentum's crashes come in rebounds after falls)
WEIGHT_REFRESH_DAYS = 365
MIN_EVIDENCE_MONTHS = 60
SUB_CAP_MIN, SUB_CAP_SHARE, STANDOUT_PCT = 4, 0.35, 0.95
N_CANDIDATES = config.JUDGED_PER_REBUILD + 10     # a little more than the team judges, so news can reorder the list
SLOT_WEIGHT = {2: 6, 1: 4, 0: 2, -1: 1, -2: 0}
MIN_PRICE, MIN_DOLLAR_VOLUME = 5.0, 3_000_000
CONTROL_SIZE = 18
INSIDER_WINDOW_DAYS, INSIDER_BACKFILL_DAYS = 90, 60
REVISION_POOL = None                     # estimate revisions for every stock (None); a number = only the top of the list
FUNDAMENTALS_MAX_AGE_DAYS = 100          # re-read a company's filings at least this often
ACQUISITION_FORMS = {"DEFM14A", "PREM14A", "DEFM14C", "PREM14C", "SC TO-T", "SC TO-T/A", "SC 14D9", "SC 14D9/A"}
EARNINGS_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "8-K"}


# ==================================================================== 1. universe
def load_universe(get=requests.get):
    frames = []
    for index, url in WIKI.items():
        html = get(url, headers=UA, timeout=30).text
        for t in pd.read_html(io.StringIO(html)):
            cols = {str(c) for c in t.columns}
            sector_col = next((c for c in t.columns if "Sector" in str(c)), None)
            if "Symbol" in cols and sector_col is not None:
                name_col = next((c for c in ("Security", "Company") if c in cols), t.columns[1])
                sub_col = next((c for c in t.columns if "Sub-Industry" in str(c)), None)
                frames.append(pd.DataFrame({
                    "ticker": t["Symbol"].astype(str).str.strip().str.replace("-", ".", regex=False),
                    "name": t[name_col].astype(str), "index": index,
                    "sector": t[sector_col].astype(str).map(lambda s: GICS_TO_SECTOR.get(s, s)),
                    "sub_industry": t[sub_col].astype(str) if sub_col is not None else ""}))
                break
    uni = pd.concat(frames).drop_duplicates("ticker").reset_index(drop=True)
    uni = uni[uni.sector.isin(config.SECTORS)]
    uni["kind"] = uni.apply(kind_of, axis=1)
    return uni


def kind_of(row):
    sub = str(row.get("sub_industry", ""))
    if row["sector"] == "Real Estate" or "REIT" in sub:
        return "reit"
    if "Bank" in sub or "Thrift" in sub:
        return "bank"
    if "Insurance" in sub or "Reinsurance" in sub:
        return "insurer"
    return "company"


# ==================================================================== 2. prices
def load_prices(tickers):
    import yfinance as yf
    ysyms = [t.replace(".", "-") for t in tickers]
    data = yf.download(ysyms, period="15mo", progress=False, auto_adjust=True, threads=True)
    close, vol = data["Close"], data["Volume"]
    close.columns = [c.replace("-", ".") for c in close.columns]
    vol.columns = [c.replace("-", ".") for c in vol.columns]
    return close, vol


def price_signals(close, vol):
    out = {}
    rets = close.pct_change(fill_method=None)
    market = rets.mean(axis=1)                 # equal-weighted universe: "the market" for residual momentum
    for t in close.columns:
        s = close[t].dropna()
        if len(s) < 70:
            continue
        v = vol[t].reindex(s.index).fillna(0)
        r = {"price": float(s.iloc[-1]), "dollar_volume": float((s * v).tail(20).mean()),
             "first_price": s.index[0].date().isoformat(),
             "vol_60d": float(s.pct_change().tail(60).std() * math.sqrt(252))}
        r["mom_3m"] = float(s.iloc[-1] / s.iloc[-64] - 1) if len(s) > 64 else np.nan
        r["mom_12_1"] = float(s.iloc[-22] / s.iloc[-253] - 1) if len(s) > 253 else np.nan
        r["mom_1m"] = float(s.iloc[-1] / s.iloc[-22] - 1) if len(s) > 22 else np.nan
        r["high_52w"] = float(s.iloc[-1] / s.tail(252).max()) if len(s) > 200 else np.nan
        r.update(risk_signals(rets[t], market, r["mom_12_1"], r["vol_60d"]))
        out[t] = r
    return pd.DataFrame.from_dict(out, orient="index")


def risk_signals(r, market, mom_12_1, vol_60d):
    """1-year and blended volatility, risk-adjusted momentum and residual momentum for one stock."""
    r = r.dropna()
    out = {"vol_252d": np.nan, "vol_blend": vol_60d, "mom_riskadj": np.nan, "mom_resid": np.nan, "info_discrete": np.nan}
    if len(r) < 200:
        return out
    r = r.tail(252)
    v252 = float(r.std() * math.sqrt(252))
    out["vol_252d"] = v252
    # blended: one earnings jump can double 60-day volatility; the 1-year figure steadies it
    out["vol_blend"] = float(math.sqrt(0.5 * vol_60d ** 2 + 0.5 * v252 ** 2)) if vol_60d == vol_60d else v252
    if mom_12_1 == mom_12_1 and v252 > 0:
        out["mom_riskadj"] = float(mom_12_1 / v252)
    rw = r.iloc[:-21]                          # the 12-1 month window: share of up vs down days
    if len(rw) > 150 and mom_12_1 == mom_12_1:
        out["info_discrete"] = float(np.sign(mom_12_1) * ((rw < 0).mean() - (rw > 0).mean()))
    m = market.reindex(r.index).fillna(0)
    if m.var() > 0:
        beta = float(r.cov(m) / m.var())
        resid = r - beta * m
        window = resid.iloc[:-21]              # skip the latest month, like plain momentum
        sd = float(resid.std())
        if sd > 0 and len(window) > 150:
            out["mom_resid"] = float(window.sum() / (sd * math.sqrt(len(window))))
    return out


# ==================================================================== 3a. SEC filings (cached)
def sec_refresh(sec, uni):
    """Walk new daily filing indexes since last run. Returns (companies with new filings,
    insider buys table, acquisition flags). Everything is cached in state/."""
    st = read_json(state_path("sec_state.json"), {})
    start = (pd.Timestamp(st["last_index_date"]).date() + timedelta(days=1)
             if st.get("last_index_date") else TODAY - timedelta(days=INSIDER_BACKFILL_DAYS))
    ciks = set(uni.cik.dropna().astype(int))
    filers, buys, acq = set(), [], dict(st.get("acquisition_flags", {}))
    d, n_forms = start, 0
    while d <= TODAY:
        if d.weekday() < 5:
            for f in sec.daily_index(d):
                if f["cik"] not in ciks:
                    continue
                if f["form"] in EARNINGS_FORMS:
                    filers.add(f["cik"])
                if f["form"] in ACQUISITION_FORMS:
                    filed = re.sub(r"^(\d{4})(\d{2})(\d{2})$", r"\1-\2-\3", f["filed"])
                    acq[str(f["cik"])] = f"{f['form']} filed {filed}"
                if f["form"] == "4":
                    n_forms += 1
                    for p in sec.form4_purchases(f["file"]):
                        if p["issuer_cik"] == f["cik"] and p["value"] > 0:
                            buys.append(p)
        d += timedelta(days=1)
    path = state_path("insider_buys.csv")
    old = pd.read_csv(path) if path.exists() else pd.DataFrame()
    allbuys = pd.concat([old, pd.DataFrame(buys)], ignore_index=True)
    if len(allbuys):
        allbuys = allbuys.drop_duplicates(["issuer_cik", "owner", "date", "shares", "price"])
        allbuys = allbuys[pd.to_datetime(allbuys.date, errors="coerce") >= pd.Timestamp(TODAY - timedelta(days=365))]
        allbuys.to_csv(path, index=False)
    cutoff = (TODAY - timedelta(days=60)).isoformat()
    acq = {k: v for k, v in acq.items() if v.split("filed ")[-1] >= cutoff}
    # companies that filed since the base-rate job last looked (it refreshes their earnings dates)
    st["filers_since_history"] = sorted(set(st.get("filers_since_history", [])) | set(filers))
    st.update({"last_index_date": TODAY.isoformat(), "acquisition_flags": acq})
    write_json(state_path("sec_state.json"), st)
    print(f"    SEC: {len(filers)} companies filed, {n_forms} Form 4s read, {len(buys)} new insider buys")
    return filers, allbuys, acq


def fundamentals(sec, uni, filers):
    cache = read_json(state_path("fundamentals_cache.json"), {})
    from .sec import METRICS_VERSION
    todo = [c for c in uni.cik.dropna().astype(int)
            if str(c) not in cache or c in filers or cache[str(c)].get("v") != METRICS_VERSION
            or (TODAY - pd.Timestamp(cache[str(c)].get("fetched", "2000-01-01")).date()).days > FUNDAMENTALS_MAX_AGE_DAYS]
    print(f"    SEC fundamentals: refreshing {len(todo)} of {uni.cik.notna().sum()} companies")
    for i, cik in enumerate(todo, 1):
        try:
            m = sec.metrics(cik)
            if m:
                cache[str(cik)] = dict(m, fetched=TODAY.isoformat())
        except Exception as e:
            print(f"    ! SEC {cik}: {str(e)[:80]}")
        if i % 200 == 0:
            print(f"      {i}/{len(todo)}")
            write_json(state_path("fundamentals_cache.json"), cache)
    write_json(state_path("fundamentals_cache.json"), cache)
    return cache


def fundamental_signals(row, f, price):
    """Quality and value inputs appropriate to the company type. Higher = better for all."""
    g = lambda k: f.get(k) if f else None
    assets, shares = g("assets"), g("shares")
    mcap = price * shares if shares and price else None
    q, v = {}, {}
    div = lambda a, b: a / b if a is not None and b not in (None, 0) else None
    if row.kind in ("bank", "insurer"):
        q["roa"] = div(g("net_income"), assets)
        q["equity_to_assets"] = div(g("equity"), assets)
        v["earnings_yield"] = div(g("net_income"), mcap)
        v["book_yield"] = div(g("equity"), mcap)
    elif row.kind == "reit":
        ffo = (g("net_income") or 0) + (g("dna") or 0) if g("net_income") is not None else None
        q["ffo_to_assets"] = div(ffo, assets)
        lev = div(g("debt"), assets)
        q["low_leverage"] = -lev if lev is not None else None
        v["ffo_yield"] = div(ffo, mcap)
    else:
        q["x_fscore"] = g("fscore")                    # built for operating companies, not banks or REITs
        q["gross_profitability"] = div(g("gross_profit"), assets)
        q["op_margin"] = div(g("operating_income"), g("revenue"))
        acc = div((g("net_income") or 0) - (g("cfo") or 0), assets) if g("net_income") is not None and g("cfo") is not None else None
        q["low_accruals"] = -acc if acc is not None else None
        lev = div(g("debt"), assets)
        q["low_leverage"] = -lev if lev is not None else None
        q["x_roic"] = g("roic")                        # x_ = candidate signal inputs, not part of quality yet
        q["x_margin_stability"] = g("margin_stability")
        fcf = g("cfo") - (g("capex") or 0) if g("cfo") is not None else None
        v["fcf_yield"] = div(fcf, mcap)
        ev = mcap + (g("debt") or 0) - (g("cash") or 0) if mcap else None
        v["ebit_yield"] = div(g("operating_income"), ev)
    # candidate inputs for every company type (x_ = not part of the quality average)
    q["x_net_issuance"] = -g("share_growth") if g("share_growth") is not None else None
    q["x_low_asset_growth"] = -g("asset_growth") if g("asset_growth") is not None else None
    return q, v, mcap


# ==================================================================== 3b. earnings momentum
def finnhub_earnings(tickers, filers_tickers, get=requests.get):
    key = os.environ.get("FINNHUB_API_KEY")
    cache = read_json(state_path("earnings_cache.json"), {})
    if not key:
        print("    ! FINNHUB_API_KEY not set: earnings surprises scored neutral")
        return cache
    todo = [t for t in tickers if t not in cache or t in filers_tickers
            or (TODAY - pd.Timestamp(cache[t].get("fetched", "2000-01-01")).date()).days > FUNDAMENTALS_MAX_AGE_DAYS]
    print(f"    Finnhub surprises: refreshing {len(todo)} (about {len(todo) // 55 + 1} min)")
    for t in todo:
        try:
            r = get("https://finnhub.io/api/v1/stock/earnings", params={"symbol": t, "token": key}, timeout=20)
            if r.status_code == 429:
                time.sleep(30)
                r = get("https://finnhub.io/api/v1/stock/earnings", params={"symbol": t, "token": key}, timeout=20)
            rows = r.json() if r.status_code == 200 else []
            sp = [x.get("surprisePercent") for x in rows[:2] if isinstance(x, dict) and x.get("surprisePercent") is not None]
            cache[t] = {"surprise": (0.6 * sp[0] + 0.4 * sp[1]) if len(sp) == 2 else (sp[0] if sp else None),
                        "fetched": TODAY.isoformat()}
        except Exception:
            pass
        time.sleep(1.05)
        if len(cache) % 100 == 0:
            write_json(state_path("earnings_cache.json"), cache)
    write_json(state_path("earnings_cache.json"), cache)
    return cache


def earnings_calendar(get=requests.get):
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return {}
    try:
        r = get("https://finnhub.io/api/v1/calendar/earnings", timeout=30, params={
            "from": TODAY.isoformat(), "to": (TODAY + timedelta(days=35)).isoformat(), "token": key})
        return {x["symbol"].replace("-", "."): x["date"] for x in r.json().get("earningsCalendar", [])}
    except Exception:
        return {}


def revisions(tickers):
    """Net estimate revisions over 30 days, current quarter + year (Yahoo, unofficial)."""
    cache = read_json(state_path("revisions_cache.json"), {})
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    fails = 0
    for t in tickers:
        c = cache.get(t)
        if c and (TODAY - pd.Timestamp(c["fetched"]).date()).days < 6:
            out[t] = c["net"]
            continue
        net = None
        try:
            df = yf.Ticker(t.replace(".", "-")).eps_revisions
            if df is not None and len(df):
                df.columns = [str(c).lower() for c in df.columns]
                up = next((c for c in df.columns if c.startswith("up") and "30" in c), None)
                dn = next((c for c in df.columns if c.startswith("down") and "30" in c), None)
                vals = []
                for per in ("0q", "0y"):
                    if per in df.index and up and dn:
                        u, d = float(df.loc[per, up] or 0), float(df.loc[per, dn] or 0)
                        if u + d > 0:
                            vals.append((u - d) / (u + d))
                net = float(np.mean(vals)) if vals else None
        except Exception as e:
            net = None
            fails += 1
            if fails >= 25:                     # Yahoo throttling us: stop, the rest score neutral this week
                print(f"    ! estimate revisions: Yahoo refused {fails} requests in a row ({str(e)[:60]}); "
                      f"stopping at {len(out)} of {len(tickers)} (the rest score neutral)")
                break
        else:
            fails = 0
        cache[t] = {"net": net, "fetched": TODAY.isoformat()}
        out[t] = net
        time.sleep(0.8)                         # spread out: ~1,500 stocks in about half an hour
        if len(out) % 50 == 0:
            write_json(state_path("revisions_cache.json"), cache)
    write_json(state_path("revisions_cache.json"), cache)
    return out


# ==================================================================== 3c. insider
def insider_scores(buys, uni):
    if buys is None or not len(buys):
        return {}
    b = buys[pd.to_datetime(buys.date, errors="coerce") >= pd.Timestamp(TODAY - timedelta(days=INSIDER_WINDOW_DAYS))]
    out = {}
    for cik, g in b.groupby("issuer_cik"):
        out[int(cik)] = {"buy_value": float(g.value.sum()), "buyers": int(g.owner.nunique())}
    return out


# ==================================================================== 4. scoring
def sector_rank(df, col, group_cols=("sector",)):
    """Percentile rank within group, 0..1; missing -> NaN (scored neutral later)."""
    return df.groupby(list(group_cols))[col].rank(pct=True)


def t_min(k):
    return CANDIDATE_T_MIN_NEW.get(k, CANDIDATE_T_MIN)


def family_of(k):
    return next((f for f, ms in FAMILIES.items() if k in ms), k)


def _halfway(prior, ev):
    """Move each prior weight halfway toward its share of the positive evidence, keeping the total of the
    tested ones. prior: {name: weight}; ev: {name: IC or None (untested)}."""
    tested = {k: max(0.0, v) for k, v in ev.items() if v is not None}
    out = dict(prior)
    share, pos = sum(prior[k] for k in tested), sum(tested.values())
    if tested and pos > 0:
        for k in tested:
            out[k] = 0.5 * prior[k] + 0.5 * share * tested[k] / pos
    return out


def market_12m(close):
    """The equal-weighted market's return over the last 252 trading days (None with too little history)."""
    if close is None or len(close) < 253:
        return None
    mkt = (1 + close.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    return float(mkt.iloc[-1] / mkt.iloc[-253] - 1)


def momentum_guard(weights, m12):
    """(weights, on): with the guard on, the momentum family's weight is shared out among the other signals."""
    if not MOMENTUM_GUARD or m12 is None or m12 >= 0:
        return weights, False
    kept = {k: (0.0 if k in FAMILIES["momentum"] else v) for k, v in weights.items()}
    tot, was = sum(kept.values()), sum(weights.values())
    if tot <= 0:
        return weights, False
    return {k: round(v * was / tot, 4) for k, v in kept.items()}, True


def screen_weights(evidence=None, saved=None, today=None):
    """Starting weights moved halfway toward the evidence, re-set at most once a year (or when new signals
    get tested, or the rule changes). Rules:
      - a candidate (starting weight 0) counts only if its t-stat clears its bar (1.5; 2.0 for the newest);
      - overlapping signals share their family's budget (momentum, quality): first the families and
        stand-alone signals are weighed against each other, then each family's weight is split among
        its members the same way, so a variant can only reshuffle weight inside its family."""
    today = today or TODAY
    saved = saved if saved is not None else (read_json(state_path("screen_weights.json")) or {})
    ev = (evidence if evidence is not None else (read_json(state_path("signal_evidence.json")) or {})).get("signals", {})
    tested = {k: v for k, v in ev.items() if k in PRIOR_WEIGHTS and v.get("months", 0) >= MIN_EVIDENCE_MONTHS}
    newly = set(tested) - set(saved.get("evidence") or {})
    if (saved.get("set") and saved.get("rule") == WEIGHT_RULE and not newly
            and (today - pd.Timestamp(saved["set"]).date()).days < WEIGHT_REFRESH_DAYS):
        return {**{k: 0.0 for k in PRIOR_WEIGHTS}, **saved["weights"]}, saved

    def ic(k):
        """The IC that counts: established signals always; candidates only past their bar."""
        v = tested.get(k)
        if v is None:
            return None
        if PRIOR_WEIGHTS[k] == 0 and (v.get("t") or 0) < t_min(k):
            return 0.0
        return v["mean_ic"]

    units = {}
    for k in PRIOR_WEIGHTS:
        units.setdefault(family_of(k), []).append(k)
    uprior = {u: sum(PRIOR_WEIGHTS[k] for k in ms) for u, ms in units.items()}
    uev = {}
    for u, ms in units.items():
        # a family's total is judged on its established members only, so a strong new variant reshuffles
        # weight inside the family but never adds to it
        if len(ms) == 1:
            uev[u] = ic(ms[0])
            continue
        vals = [ic(k) for k in ms if ic(k) is not None and PRIOR_WEIGHTS[k] > 0]
        uev[u] = max(vals) if vals else None
    uw = _halfway(uprior, uev)
    w = {}
    for u, ms in units.items():
        if len(ms) == 1:
            w[ms[0]] = uw[u]
            continue
        inner = _halfway({k: PRIOR_WEIGHTS[k] / uprior[u] for k in ms}, {k: ic(k) for k in ms})
        tot = sum(inner.values()) or 1
        for k in ms:
            w[k] = uw[u] * inner[k] / tot
    tot = sum(w.values())
    w = {k: round(v / tot, 4) for k, v in w.items()}
    if tested:
        saved = {"set": today.isoformat(), "rule": WEIGHT_RULE, "weights": w, "evidence": tested}
        write_json(state_path("screen_weights.json"), saved)
    return w, saved


def signal_verdicts(evidence):
    """Signals that add nothing (or hurt) over 15 years are flagged for removal (your approval)."""
    out = {}
    for k, v in (evidence or {}).get("signals", {}).items():
        t = v.get("t")
        if v.get("months", 0) < MIN_EVIDENCE_MONTHS or t is None:
            out[k] = "not enough history"
        elif t <= -2:
            out[k] = "HURTS: candidate for removal (needs your approval)"
        elif abs(t) < 1:
            out[k] = "adds nothing: candidate for removal (needs your approval)"
        else:
            out[k] = "keep"
    return out


def distressed(df):
    """High debt, negative free cash flow and operating losses together: these blow up more often than
    their momentum suggests. Banks, insurers and REITs are judged by their own measures, not this."""
    lev = -df.get("q_low_leverage", pd.Series(np.nan, index=df.index))
    fcf = df.get("v_fcf_yield", pd.Series(np.nan, index=df.index))
    om = df.get("q_op_margin", pd.Series(np.nan, index=df.index))
    return (df.kind == "company") & (lev > 0.6) & (fcf < 0) & (om < 0)


def score(df, feats=None, weights=None):
    groups = ("sector", "kind")
    weights = weights or WEIGHTS
    feats = feats or {}
    # momentum: 70% 12-1 month, 30% 3-month
    df["s_momentum"] = 0.7 * sector_rank(df, "mom_12_1", groups).fillna(0.5) + 0.3 * sector_rank(df, "mom_3m", groups).fillna(0.5)
    # earnings: surprises + revisions (revisions only exist for the top pool; others neutral)
    df["s_earnings"] = 0.5 * sector_rank(df, "surprise", groups).fillna(0.5) + 0.5 * sector_rank(df, "revisions", groups).fillna(0.5)
    # post-earnings drift: the stock's move vs its sector around its latest earnings (last 100 days)
    df["reaction"] = df.ticker.map(lambda t: (feats.get(t) or {}).get("reaction_now_%"))
    df["s_reaction"] = sector_rank(df, "reaction", groups).fillna(0.5)
    # industry momentum: the sub-industry's average 12-1 month return, ranked within the sector
    grp = "sub_industry" if "sub_industry" in df else "sector"
    df["industry_mom"] = df.groupby(grp)["mom_12_1"].transform("mean")
    df["s_industry"] = sector_rank(df, "industry_mom", ("sector",)).fillna(0.5)
    # short-term reversal: last month's big winners tend to give some back
    df["neg_mom_1m"] = -df["mom_1m"] if "mom_1m" in df else np.nan
    df["s_reversal"] = sector_rank(df, "neg_mom_1m", groups).fillna(0.5)
    qcols = [c for c in df.columns if c.startswith("q_") and not c.startswith("q_x_")]
    # candidate signals (zero weight until history supports them)
    df["s_resid_momentum"] = sector_rank(df, "mom_resid", groups).fillna(0.5) if "mom_resid" in df else 0.5
    df["s_riskadj_momentum"] = sector_rank(df, "mom_riskadj", groups).fillna(0.5) if "mom_riskadj" in df else 0.5
    df["neg_vol"] = -df["vol_blend"] if "vol_blend" in df else np.nan
    df["s_low_vol"] = sector_rank(df, "neg_vol", groups).fillna(0.5)
    df["s_roic"] = sector_rank(df, "q_x_roic", groups).fillna(0.5) if "q_x_roic" in df else 0.5
    df["s_stability"] = sector_rank(df, "q_x_margin_stability", groups).fillna(0.5) if "q_x_margin_stability" in df else 0.5
    # frog in the pan: momentum from many small moves counts more than momentum from a few jumps
    if "info_discrete" in df:
        df["frog"] = (df.groupby(list(groups))["mom_12_1"].rank(pct=True) - 0.5) * (1 - df["info_discrete"])
    df["neg_short"] = -df["days_to_cover"] if "days_to_cover" in df else np.nan
    for sig, col in (("frog_momentum", "frog"), ("low_short", "neg_short"), ("filing_similarity", "filing_similarity"),
                     ("high_52w", "high_52w"), ("fscore", "q_x_fscore"), ("net_issuance", "q_x_net_issuance"),
                     ("asset_growth", "q_x_low_asset_growth")):
        df[f"s_{sig}"] = sector_rank(df, col, groups).fillna(0.5) if col in df else 0.5
    vcols = [c for c in df.columns if c.startswith("v_")]
    df["s_quality"] = pd.concat([sector_rank(df, c, groups) for c in qcols], axis=1).mean(axis=1).fillna(0.5) if qcols else 0.5
    df["s_value"] = pd.concat([sector_rank(df, c, groups) for c in vcols], axis=1).mean(axis=1).fillna(0.5) if vcols else 0.5
    # insider: no buys = neutral 0.5; buys scale 0.6-1.0 by size relative to market cap, +bonus for clusters
    rel = (df.insider_value / df.mcap).where(df.insider_value > 0)
    r = rel.rank(pct=True)
    df["s_insider"] = np.where(df.insider_value > 0, 0.6 + 0.3 * r.fillna(0) + np.where(df.insider_buyers >= 3, 0.1, 0), 0.5)
    df["composite"] = sum(weights.get(k, 0) * df[f"s_{k}"] for k in PRIOR_WEIGHTS)
    return df


def pick_candidates(pool, slots, held, standout_cut):
    """Top names per sector by composite, with at most max(4, 35% of the sector's slots) per sub-industry.
    Standouts (top 5% of the universe) and holdings are never capped. Returns (candidates, bumped,
    replacements): bumped = names the cap kept out; replacements = the names that took their places."""
    picks, bumped, repl = [], [], []
    for sector, n in slots.items():
        if n <= 0:
            continue
        g = pool[pool.sector == sector].sort_values("composite", ascending=False)
        cap = max(SUB_CAP_MIN, int(np.ceil(SUB_CAP_SHARE * n)))
        count, chosen, out = {}, [], []
        grp = "sub_industry" if "sub_industry" in g else "sector"
        for r in g.itertuples():
            if len(chosen) >= n:
                break
            k = getattr(r, grp)
            exempt = r.composite >= standout_cut or r.ticker in held
            if count.get(k, 0) >= cap and not exempt:
                out.append(r.ticker)
                continue
            count[k] = count.get(k, 0) + 1
            chosen.append(r.ticker)
        uncapped = list(g.head(n).ticker)
        repl += [t for t in chosen if t not in uncapped]
        bumped += [t for t in out if t in uncapped]
        picks += chosen
    return pool[pool.ticker.isin(picks)], bumped, repl


# ==================================================================== 5. slots & control
def allocate_slots(tilts, available):
    w = {s: SLOT_WEIGHT[int(tilts.get(s, 0))] for s in config.SECTORS}
    total = sum(w.values()) or 1
    raw = {s: N_CANDIDATES * w[s] / total for s in w}
    slots = {s: min(int(raw[s]), available.get(s, 0)) for s in w}
    # hand out the remainder by largest fraction, then any unused slots to the best-tilted sectors
    order = sorted(w, key=lambda s: (-(raw[s] - int(raw[s])), -w[s]))
    while sum(slots.values()) < N_CANDIDATES:
        grew = False
        for s in order + sorted(w, key=lambda s: -w[s]):
            if w[s] > 0 and slots[s] < available.get(s, 0) and sum(slots.values()) < N_CANDIDATES:
                slots[s] += 1
                grew = True
        if not grew:
            break
    return slots


def control_portfolio(ranked, macro):
    """Screen-only control: top stocks by composite under the same sector ceilings, inverse-vol sized."""
    ranges = (macro or {}).get("weight_ranges_%", {})
    picks, count = [], {}
    for _, r in ranked.iterrows():
        cap = ranges.get(r.sector, [0, 15])[1]
        max_n = int(cap / 100 * CONTROL_SIZE)          # whole positions that fit under the ceiling
        if count.get(r.sector, 0) < max_n:
            picks.append(r)
            count[r.sector] = count.get(r.sector, 0) + 1
        if len(picks) == CONTROL_SIZE:
            break
    inv = np.array([1 / max(p.vol_60d, 0.05) for p in picks])
    w = np.clip(inv / inv.sum(), 0.03, 0.10)
    w = w / w.sum()
    return [{"ticker": p.ticker, "sector": p.sector, "weight_%": round(float(x) * 100, 2)} for p, x in zip(picks, w)]


# ==================================================================== MAIN
def main(session, folder, sec=None, get=requests.get):
    sec = sec or SEC()
    print("1/6 Universe...")
    uni = load_universe(get)
    tmap = sec.ticker_map()
    uni["cik"] = uni.ticker.map(tmap)
    print(f"    {len(uni)} stocks ({uni.cik.isna().sum()} without an SEC match)")

    print("2/6 Prices and liquidity...")
    close, vol = load_prices(list(uni.ticker))
    px = price_signals(close, vol)
    df = uni.join(px, on="ticker")
    before = len(df)
    df = df[(df.price > MIN_PRICE) & (df.dollar_volume > MIN_DOLLAR_VOLUME)].copy()
    print(f"    {len(df)} pass price/liquidity filters ({before - len(df)} removed)")

    print("3/6 SEC filings: fundamentals, insider buys, deal flags...")
    filers, buys, acq = sec_refresh(sec, df)
    fcache = fundamentals(sec, df, filers)
    qrows, vrows, mcaps, stale = [], [], [], []
    for r in df.itertuples():
        f = fcache.get(str(int(r.cik))) if pd.notna(r.cik) else None
        q, v, mcap = fundamental_signals(r, f, r.price)
        qrows.append(q)
        vrows.append(v)
        mcaps.append(mcap)
        stale.append(bool(f and f.get("stale")))
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(qrows).add_prefix("q_"), pd.DataFrame(vrows).add_prefix("v_")], axis=1)
    df["mcap"], df["fundamentals_stale"] = mcaps, stale
    ins = insider_scores(buys, df)
    df["insider_value"] = [ins.get(int(c), {}).get("buy_value", 0.0) if pd.notna(c) else 0.0 for c in df.cik]
    df["insider_buyers"] = [ins.get(int(c), {}).get("buyers", 0) if pd.notna(c) else 0 for c in df.cik]

    print("4/6 Earnings momentum...")
    filer_tickers = set(df[df.cik.isin(filers)].ticker)
    ecache = finnhub_earnings(list(df.ticker), filer_tickers, get)
    df["surprise"] = [ecache.get(t, {}).get("surprise") for t in df.ticker]
    df["surprise"] = df.surprise.clip(-50, 50)
    df["revisions"] = np.nan
    from .altdata import latest_lazy, latest_short, norm_symbol
    si_date, si = latest_short(get)
    df["days_to_cover"] = pd.to_numeric(pd.Series([si.get(norm_symbol(t)) for t in df.ticker], index=df.index), errors="coerce")
    df["filing_similarity"] = pd.to_numeric(df.ticker.map(latest_lazy()), errors="coerce")
    print(f"    FINRA short interest {si_date or 'unavailable'}: {df.days_to_cover.notna().sum()} stocks; "
          f"10-K similarity: {df.filing_similarity.notna().sum()} stocks")
    feats = (read_json(state_path("current_features.json"), {}) or {}).get("stocks", {})
    weights, wsaved = screen_weights()
    m12 = market_12m(close)
    weights, guard_on = momentum_guard(weights, m12)
    print(f"    momentum guard {'ON: momentum signals carry no weight' if guard_on else 'off'}"
          + (f" (equal-weighted market, last 12 months: {m12 * 100:+.1f}%)" if m12 is not None else " (not enough price history)"))
    evidence = read_json(state_path("signal_evidence.json")) or {}
    df = score(df, feats, weights)                          # first pass without revisions
    holdings = read_json(state_path("holdings.json"), {}) or {}
    held = {p["ticker"] for p in holdings.get("positions", [])}
    pool = (set(df.ticker) if REVISION_POOL is None else set(df.nlargest(REVISION_POOL, "composite").ticker)) | (held & set(df.ticker))
    rev = revisions(sorted(pool))
    df["revisions"] = df.ticker.map(rev)
    df = score(df, feats, weights)                          # final scores

    print("5/6 Macro slots, flags, candidates...")
    macro = config.with_current_ranges(read_json(state_path("macro_view.json")))
    tilts = (macro or {}).get("tilts", {})
    cal = earnings_calendar(get)
    horizon = (TODAY + timedelta(days=30)).isoformat()
    df["earnings_date"] = df.ticker.map(cal)
    df["flags"] = [", ".join(x for x in (
        f"earnings {d}" if isinstance(d, str) and d <= horizon else "",
        f"possible acquisition ({acq[str(int(c))]})" if pd.notna(c) and str(int(c)) in acq else "",
        "old filings" if s else "") if x) for d, c, s in zip(df.earnings_date, df.cik, df.fundamentals_stale)]
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["rank_in_sector"] = df.groupby("sector").cumcount() + 1
    # no new buys of stocks with under 12 months of trading (recent IPOs and spinoffs)
    young_cut = (TODAY - timedelta(days=config.MIN_HISTORY_DAYS)).isoformat()
    df["young"] = df.first_price.fillna(TODAY.isoformat()) > young_cut
    if df.young.any():
        print(f"    {int(df.young.sum())} stocks with under 12 months of history excluded from new candidates")
    df["distressed"] = distressed(df)
    if df.distressed.any():
        print(f"    {int(df.distressed.sum())} distressed stocks (high debt, cash burn, losses) excluded from new candidates")
    pool = df[~df.young & ~df.distressed]
    slots = allocate_slots(tilts, pool.sector.value_counts().to_dict())
    standout = float(df.composite.quantile(STANDOUT_PCT))
    cands, bumped, repl = pick_candidates(pool, slots, held, standout)
    if bumped:
        print(f"    sub-industry cap kept out {len(bumped)} names: {bumped[:10]}")
    inc = df[df.ticker.isin(held) & ~df.ticker.isin(cands.ticker)]
    cands = pd.concat([cands.assign(incumbent=cands.ticker.isin(held)), inc.assign(incumbent=True)])
    cands = cands.sort_values("composite", ascending=False)

    print("6/6 Saving...")
    keep = ["ticker", "name", "index", "sector", "sub_industry", "kind", "composite", "s_momentum", "s_earnings",
            "s_quality", "s_value", "s_insider", "mom_12_1", "mom_3m", "surprise", "revisions", "insider_value",
            "insider_buyers", "price", "mcap", "vol_60d", "dollar_volume", "earnings_date", "flags", "rank_in_sector", "cik",
            "first_price", "s_reaction", "s_industry", "s_reversal", "mom_1m", "reaction", "distressed",
            "vol_252d", "vol_blend", "mom_riskadj", "mom_resid", "s_resid_momentum", "s_riskadj_momentum", "s_low_vol",
            "s_roic", "s_stability", "high_52w", "s_high_52w", "s_fscore", "s_net_issuance", "s_asset_growth",
            "frog", "s_frog_momentum", "days_to_cover", "s_low_short", "filing_similarity", "s_filing_similarity"]
    keep += [c for c in df.columns if c.startswith(("q_", "v_"))]
    df[keep].to_csv(state_path("bench.csv"), index=False)
    df[keep].to_csv(folder / "bench.csv", index=False)
    control = control_portfolio(df, macro)
    out = {"date": TODAY.isoformat(), "macro_view_date": (macro or {}).get("date"), "tilts": tilts, "slots": slots,
           "weights": weights, "momentum_guard": {"on": guard_on, "market_12m": None if m12 is None else round(m12, 4)},
           "cap_bumped": bumped, "cap_replacements": repl,
           "candidates": json.loads(cands[keep + ["incumbent"]].to_json(orient="records")),
           "control_portfolio": control}
    write_json(state_path("candidates.json"), out)
    hist = read_json(state_path("signal_history.json"), {})
    q = max(1, len(df) // 5)
    hist[TODAY.isoformat()] = {name: {"top": list(df.nlargest(q, col).ticker), "bottom": list(df.nsmallest(q, col).ticker)}
                               for name, col in [(k, f"s_{k}") for k in PRIOR_WEIGHTS] + [("composite", "composite")]}
    if bumped:        # graded like a signal: if kept-out names beat their replacements, the cap is too tight
        hist[TODAY.isoformat()]["cap_bumped_vs_replacements"] = {"top": bumped, "bottom": repl}
    write_json(state_path("signal_history.json"), dict(sorted(hist.items())[-60:]))
    write_json(folder / "candidates.json", out)
    (folder / "report.md").write_text(report(df, cands, slots, tilts, control, macro, weights, evidence, bumped, repl))
    print(f"    {len(cands)} candidates ({int(cands.incumbent.sum())} current holdings)")
    return {"candidates": len(cands)}


def report(df, cands, slots, tilts, control, macro, weights=None, evidence=None, bumped=(), repl=()):
    weights = weights or WEIGHTS
    L = [f"# Screen, {TODAY}", f"Universe after filters: {len(df)} stocks. Macro view: {(macro or {}).get('date', 'none (all neutral)')}", "",
         "## Signal weights and what history says about them",
         "Candidates need t ≥ 1.5 (2.0 for the newest) to earn weight; momentum and quality variants share their "
         "family's budget.", "",
         "| Signal | Family | Weight | Starting weight | 15-yr IC | t | Verdict |", "|---|---|---|---|---|---|---|"]
    ev = (evidence or {}).get("signals", {})
    verdicts = signal_verdicts(evidence)
    for k in PRIOR_WEIGHTS:
        e = ev.get(k, {})
        cand = PRIOR_WEIGHTS[k] == 0
        verdict = verdicts.get(k, 'not tested yet' if cand else 'no history (weight fixed)')
        if cand and e.get("t") is not None and e.get("months", 0) >= MIN_EVIDENCE_MONTHS:
            verdict = "earns weight" if e["t"] >= t_min(k) else f"below its bar (needs t ≥ {t_min(k)})"
        fam = family_of(k)
        L.append(f"| {k}{' (candidate)' if cand else ''} | {fam if fam != k else ''} | {weights.get(k, 0):.2f} | "
                 f"{PRIOR_WEIGHTS.get(k, 0):.2f} | {e.get('mean_ic', '')} | {e.get('t', '')} | {verdict} |")
    L += ["", "## Candidate slots by sector", "| Sector | Tilt | Slots |", "|---|---|---|"]
    L += [f"| {s} | {int(tilts.get(s, 0)):+d} | {n} |" for s, n in slots.items()]
    if len(bumped):
        L += ["", f"**Sub-industry cap** kept out: {', '.join(bumped)}; in their places: {', '.join(repl)}"]
    if "distressed" in df and df.distressed.any():
        L += [f"**Distress filter** excluded: {', '.join(df[df.distressed].ticker)}"]
    L += ["", "## Candidates", "| # | Ticker | Sector | Score | Mom | Earn | React | Industry | Qual | Value | Insider | Rev | Flags |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(cands.itertuples(), 1):
        tag = " (held)" if r.incumbent else ""
        L.append(f"| {i} | {r.ticker}{tag} | {r.sector} | {r.composite:.2f} | {r.s_momentum:.2f} | {r.s_earnings:.2f} | "
                 f"{getattr(r, 's_reaction', 0.5):.2f} | {getattr(r, 's_industry', 0.5):.2f} | {r.s_quality:.2f} | {r.s_value:.2f} | "
                 f"{r.s_insider:.2f} | {getattr(r, 's_reversal', 0.5):.2f} | {r.flags} |")
    L += ["", "## Screen-only control portfolio", ", ".join(f"{c['ticker']} {c['weight_%']}%" for c in control), "",
          "_Scores are percentile ranks within sector and company type (0-1, 0.5 = middle or missing data)._"]
    return "\n".join(L)


if __name__ == "__main__":
    run_stage("screen", main)
