"""
MACRO AGENT  —  run:  python -m pipeline.macro     (weekly job; decides light check vs full run)
                      python -m pipeline.macro --full   (force a full run)

EVERY WEEK — LIGHT CHECK (code only, free)
  FRED data + Fed projections + market data -> regime, triggers, and a "what changed since the
  last view" digest (state/macro_check.json, read by the rebuild). Then it decides:

FULL RUN when any of these is true
  - monthly schedule: this month's jobs report AND CPI are both out, and no full run since
  - a tripwire: emergency trigger (VIX > 35, credit spreads blowing out, S&P -7% in a week), a core
    variable moving 1+ standard deviation or newly unusual, a Fed rate change, or a new dot plot
  - no macro view exists yet, more than 5 weeks since the last full run, or --full

FULL RUN
  1. Evidence   code fetches the known pages (Fed, EIA, Treasury, USTR, FactSet, ...); Gemini Flash
                extracts findings with exact quotes; code verifies each quote on the page. A theme
                whose pages can't be read falls back to Claude search on the allowed sites.
  2. Reasoning  Sonnet 5 + Opus 5.5 (batched) + Gemini Flash + Mistral Large read the SAME packet
                and forecast the ECONOMY (4-week moves in 10-yr yields, oil, the dollar, credit, and
                inflation expectations) plus small cited sector-specific adjustments.
  3. Numbers    code turns the median forecast into sector probabilities of beating SPY: each
                sector starts from how it did historically in this regime, then MEASURED
                sensitivities translate the forecast moves into sector effects. Markets price roughly
                no change in these prices, so only the part of a view that differs from market
                pricing can tilt a sector: small disagreement -> +/-1, large -> +/-2 (at most two
                sectors), with a buffer before any tilt changes.
  4. Review     auditor strips bad citations/numbers -> Sonnet logic critic. A free momentum rule
                (favor the strongest 12-month sectors) is recorded alongside as the opponent.
MACRO_MODE=neutral (a GitHub variable) turns the tilts off and skips the paid run (the 12-month
pre-registered pruning rule recommends this if the macro view beats neither opponent).
  5. Output     OK views go live in state/macro_view.json; flagged views wait for your APPROVE /
                REJECT on a GitHub issue. Baseline saved for the next tripwire checks.
"""
import json
import re
import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from . import config, ledger, market_risk
from . import checkpoint as cpt
from .inputs import factor_changes
from .approvals import check_macro, request_macro_review
from .audit import Auditor, validate_notes
from .checkpoint import Checkpoint
from .fetch import gather_direct
from .notify import send, subject_line
from .runner import run_stage
from .util import JSON_RULE, append_csv, now_et, read_json, state_path, write_json, require_columns

SECTORS = config.SECTORS
TODAY = now_et().date()

# id, label, tier, transform  (tier: core | driver | watch)
FRED = [
    ("PCEPILFE", "Core PCE inflation YoY %", "core", "yoy"),
    ("CPIAUCSL", "CPI inflation YoY %", "core", "yoy"),
    ("CPILFESL", "Core CPI inflation YoY %", "core", "yoy"),
    ("CES0500000003", "Average hourly earnings YoY %", "core", "yoy"),
    ("UNRATE", "Unemployment rate %", "core", "level"),
    ("PAYEMS", "Payrolls monthly change (thousands)", "core", "diff"),
    ("IC4WSA", "Initial jobless claims, 4-wk avg", "core", "level"),
    ("DFF", "Fed funds effective rate %", "core", "level"),
    ("DGS2", "2-yr Treasury yield %", "core", "level"),
    ("DGS10", "10-yr Treasury yield %", "core", "level"),
    ("T10Y2Y", "10-yr minus 2-yr spread", "core", "level"),
    ("BAMLH0A0HYM2", "High-yield credit spread", "core", "level"),
    ("NFCI", "Chicago Fed financial conditions (negative = loose)", "core", "level"),
    ("DCOILWTICO", "WTI crude oil $/bbl", "core", "level"),
    ("DCOILBRENTEU", "Brent crude oil $/bbl", "core", "level"),
    ("DTWEXBGS", "Trade-weighted dollar index", "driver", "level"),
    ("MORTGAGE30US", "30-yr mortgage rate %", "driver", "level"),
    ("PERMIT", "Building permits (thousands, annual rate)", "driver", "level"),
    ("TOTLL", "Bank loans & leases YoY %", "driver", "yoy"),
    ("DHHNGSP", "Henry Hub natural gas $/MMBtu", "driver", "level"),
    ("PCOPPUSDM", "Copper $/metric ton", "driver", "level"),
    ("GASREGW", "Regular gasoline $/gal", "driver", "level"),
    ("PFOODINDEXM", "Global food price index", "driver", "level"),
    ("IR", "Import prices YoY %", "driver", "yoy"),
    ("RSAFS", "Retail sales YoY %", "driver", "yoy"),
    ("PSAVERT", "Personal saving rate %", "driver", "level"),
    ("CP", "Corporate profits YoY %", "driver", "yoy"),
    ("T10YIE", "10-yr breakeven inflation %", "watch", "level"),
    ("A191RL1Q225SBEA", "Real GDP growth, annualized %", "watch", "level"),
    ("GDPNOW", "Atlanta Fed GDPNow estimate %", "watch", "level"),
    ("INDPRO", "Industrial production YoY %", "watch", "yoy"),
    ("UMCSENT", "U. Michigan consumer sentiment", "watch", "level"),
    ("VIXCLS", "VIX", "watch", "level"),
    ("OVXCLS", "Oil volatility index (OVX)", "driver", "level"),
    ("EPUTRADE", "Trade policy uncertainty index", "driver", "level"),
    ("USEPUINDXD", "Economic policy uncertainty index (daily news)", "watch", "level"),
    ("SAHMREALTIME", "Sahm rule recession indicator", "watch", "level"),
    ("ECIWAG", "Employment Cost Index (wages) YoY %", "watch", "yoy"),
    ("JTSJOL", "Job openings (thousands)", "watch", "level"),
    ("JTSQUR", "Quits rate %", "watch", "level"),
    ("DTB3", "3-month T-bill %", "watch", "level"),
    ("DRTSCILM", "Banks tightening business loan standards (net %)", "watch", "level"),
    ("PALLFNFINDEXM", "Global all-commodity price index", "watch", "level"),
    ("BOPGSTB", "U.S. trade balance ($M)", "watch", "level"),
    ("MTSDS133FMS", "Federal deficit, 12-month total ($M)", "watch", "sum12"),
    ("B235RC1Q027SBEA", "Customs duties (tariff revenue) YoY %", "watch", "yoy"),
    ("CLVMNACSCAB1GQEA19", "Euro area real GDP YoY %", "watch", "yoy"),
]
# Fed Summary of Economic Projections medians (the dot plot), pulled as data instead of searched.
SEP = [("FEDTARMD", "Fed funds rate, median projection %"),
       ("FEDTARMDLR", "Fed funds rate, longer-run median %"),
       ("JCXFEMD", "Core PCE inflation, median projection %"),
       ("UNRATEMD", "Unemployment rate, median projection %"),
       ("GDPC1MD", "Real GDP growth, median projection %")]

SEARCHES_PER_THEME = 5
THEMES = {
    "A": ("Federal Reserve", """- Latest FOMC decision and statement; dates of the next FOMC meetings
- How dispersed the latest dot plot is (how many officials above/below the median)
- Latest FOMC minutes and recent speeches by the Chair/Vice Chair: direction of bias
- Latest Beige Book: overall tone and any sector-specific comments"""),
    "B": ("Inflation, energy, trade", """- Truflation's current US inflation reading vs the latest official CPI
- Cleveland Fed inflation nowcast for the next CPI and PCE releases
- EIA Short-Term Energy Outlook oil and natural gas price forecasts; latest weekly crude
  inventories vs the 5-year average
- Tariff or trade actions in the last 4 weeks (USTR, trade.gov)
- Latest Treasury quarterly refunding announcement: size/direction of issuance"""),
    "D": ("Business surveys and the world economy", """- Latest ISM manufacturing and services PMIs vs the prior month, incl. new orders and prices paid
- Latest ECB, Bank of England and Bank of Japan decisions and their guidance
- Latest IMF and OECD global growth forecasts and how they changed"""),
    "E": ("Geopolitics", """- Wars, conflicts or military escalations in the last 4 weeks that affect oil, gas, shipping or U.S.
  companies (e.g. the Middle East incl. Iran, Russia-Ukraine), with dates and what actually happened
- Shipping chokepoint disruptions (Strait of Hormuz, Red Sea/Suez, Panama Canal); latest Drewry World
  Container Index freight rate and its change
- Latest OPEC+ production decision and next meeting date; IEA Oil Market Report supply/demand view
- New U.S. export controls (Commerce BIS) or sanctions (Treasury OFAC) in the last 4 weeks, especially
  semiconductors, China, Russia, Iran
- China-Taiwan tensions; Chinese export restrictions on rare earths or critical minerals
- NATO or U.S. defense budget decisions
- U.S. policy shocks: government shutdown or debt-ceiling deadlines and their dates"""),
    "C": ("Market expectations", """- CME FedWatch probabilities for the next two FOMC meetings
- FactSet Earnings Insight: S&P 500 forward EPS growth, direction of estimate revisions,
  forward P/E vs 5- and 10-year averages, sectors with the biggest revisions up/down
- Shiller CAPE latest value; AAII sentiment survey latest bullish/bearish %
- CFTC Commitments of Traders: speculative positioning in crude oil, gold, Treasuries"""),
}


# ==================================================================== 1. DATA
def fred_obs(sid, start):
    params = {"series_id": sid, "api_key": config.secret("FRED_API_KEY"), "file_type": "json",
              "observation_start": start}
    r = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=30)
    obs = pd.DataFrame(r.json()["observations"])
    obs = obs[obs.value != "."]
    return pd.Series(obs.value.astype(float).values, index=pd.to_datetime(obs.date)).sort_index()


def monthly(s):
    return s.resample("ME").last().ffill(limit=3)


def transform(s, how):
    if how == "level":
        return s
    m = monthly(s)
    if how == "yoy":
        return ((m / m.shift(12) - 1) * 100).dropna()
    if how == "diff":
        return m.diff().dropna()
    if how == "sum12":
        return s.rolling(12).sum().dropna()
    raise ValueError(how)


def r2(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 2)


def describe(sid, label, tier, how, raw):
    v = transform(raw, how).dropna()
    last = v.index[-1]
    m = monthly(v).dropna()
    hist = m[m.index >= last - pd.DateOffset(years=5)]
    std = hist.std() if len(hist) > 12 else np.nan
    z = (v.iloc[-1] - hist.mean()) / std if std and std > 0 else np.nan
    pct = (hist < v.iloc[-1]).mean() * 100 if len(hist) > 12 else np.nan

    def ago(months):
        mask = m.index <= last - pd.DateOffset(months=months)
        return float(m[mask].iloc[-1]) if mask.any() else None

    prior3 = ago(3)
    spacing = raw.index.to_series().diff().dt.days.median()
    max_age = 10 if spacing <= 3 else 16 if spacing <= 8 else 75 if spacing <= 40 else 200
    age = (pd.Timestamp(TODAY) - last).days
    direction = None
    if prior3 is not None and std and std > 0:
        d = (v.iloc[-1] - prior3) / std
        direction = "rising" if d > 0.25 else "falling" if d < -0.25 else "flat"
    flags = []
    if not np.isnan(z) and abs(z) >= 2:
        flags.append(f"UNUSUAL (z={z:+.1f} vs 5-yr history)")
    if age > max_age:
        flags.append(f"STALE ({age} days old)")
    return {"id": sid, "label": label, "tier": tier, "latest": r2(v.iloc[-1]), "as_of": last.date().isoformat(),
            "3m_ago": r2(prior3), "12m_ago": r2(ago(12)), "direction_3m": direction,
            "z_5yr": r2(z), "percentile_5yr": r2(pct), "flags": flags}


def load_fred():
    table, raw, missing = {}, {}, []
    long_hist = {"PAYEMS", "INDPRO", "RSAFS", "IC4WSA", "PCEPILFE", "CPILFESL", "DFF"}
    for sid, label, tier, how in FRED:
        start = "1997-01-01" if sid in long_hist else f"{TODAY.year - 7}-01-01"
        try:
            raw[sid] = fred_obs(sid, start)
            table[sid] = describe(sid, label, tier, how, raw[sid])
        except Exception as e:
            missing.append({"id": sid, "label": label, "tier": tier, "error": str(e)[:120]})
        time.sleep(0.2)
    core = [m["id"] for m in missing if m["tier"] == "core"]
    if core:
        raise RuntimeError("Core data missing, run stopped: " + ", ".join(core))
    return table, raw, missing


def load_sep():
    """Dot-plot medians by projection year: {label: {"2026": 4.1, "2027": 4.1, ...}}"""
    out, facts = {}, {}
    for sid, label in SEP:
        try:
            s = fred_obs(sid, f"{TODAY.year - 1}-01-01")
            vals = {str(d.year): round(float(v), 2) for d, v in s.items()}
            out[label] = {"series": sid, "by_year": vals}
            for y, v in vals.items():
                facts[f"SEP_{sid}_{y}"] = v
        except Exception as e:
            out[label] = {"series": sid, "error": str(e)[:80]}
        time.sleep(0.2)
    return out, facts


def market_data():
    import yfinance as yf
    tickers = list(SECTORS.values()) + ["SPY", "GC=F", "^TNX", "CL=F", "UUP", "HYG", "IEF", "TIP"]
    px = yf.download(tickers, start="1998-12-01", progress=False, auto_adjust=True)["Close"]
    return require_columns(px, ["SPY"], "the macro agent")


# ==================================================================== 2. DERIVED
REGIMES = {(1, -1): "Goldilocks (growth up, inflation down)", (1, 1): "Reflation (growth up, inflation up)",
           (-1, 1): "Stagflation risk (growth down, inflation up)",
           (-1, -1): "Disinflationary slowdown (growth down, inflation down)"}


def regime_series(raw):
    m = {k: monthly(raw[k]) for k in ("PAYEMS", "INDPRO", "RSAFS", "IC4WSA", "PCEPILFE", "CPILFESL", "DFF")
         if k in raw}
    votes = []
    if "PAYEMS" in m:
        d = m["PAYEMS"].diff()
        votes.append(np.sign(d.rolling(3).mean() - d.rolling(12).mean()))
    for k in ("INDPRO", "RSAFS"):
        if k in m:
            s = m[k]
            votes.append(np.sign(((s / s.shift(3)) ** 4 - 1) - (s / s.shift(12) - 1)))
    if "IC4WSA" in m:
        votes.append(-np.sign(m["IC4WSA"].rolling(3).mean() - m["IC4WSA"].rolling(12).mean()))
    growth = pd.concat(votes, axis=1).sum(axis=1, min_count=2)
    infl = [((m[k] / m[k].shift(3)) ** 4 - 1) - (m[k] / m[k].shift(12) - 1)
            for k in ("PCEPILFE", "CPILFESL") if k in m]
    df = pd.DataFrame({"growth": np.sign(growth), "inflation": np.sign(pd.concat(infl, axis=1).mean(axis=1))}).dropna()
    df = df[(df.growth != 0) & (df.inflation != 0)]
    df["regime"] = [REGIMES[(int(g), int(i))] for g, i in zip(df.growth, df.inflation)]
    if "DFF" in m:
        chg = (m["DFF"] - m["DFF"].shift(6)).reindex(df.index)
        df["fed"] = np.where(chg > 0.25, "hiking", np.where(chg < -0.25, "cutting", "on hold"))
    return df


def history_by_regime(reg, px):
    """Sector ETF excess return vs SPY after months with the same regime (and Fed direction).
    Uses the regime known one month earlier. Note: today's revised data, not first releases."""
    mpx = px.resample("ME").last()
    now, known = reg.iloc[-1], reg.shift(1)
    out = {"current_regime": now["regime"], "current_fed": now.get("fed"), "sectors": {}}
    for sector, etf in SECTORS.items():
        if etf not in mpx:
            continue
        row = {}
        for h in (1, 3):
            rel = ((mpx[etf].shift(-h) / mpx[etf] - 1) - (mpx["SPY"].shift(-h) / mpx["SPY"] - 1)).reindex(known.index)
            for label, mask in (("same_regime", known.regime == now["regime"]),
                                ("same_regime_and_fed", (known.regime == now["regime"]) & (known.get("fed") == now.get("fed")))):
                x = rel[mask].dropna()
                row[f"{label}_{h}m"] = ({"avg_excess_%": round(x.mean() * 100, 2), "beat_spy_%": round((x > 0).mean() * 100, 1),
                                         "n_months": len(x)} if len(x) >= 6 else {"n_months": len(x), "note": "too few cases"})
        out["sectors"][sector] = row
    return out


def momentum(px):
    out, spy = {}, px["SPY"].dropna()
    for sector, etf in SECTORS.items():
        s = px[etf].dropna()
        out[sector] = {f"excess_vs_spy_{lab}_%": round(((s.iloc[-1] / s.iloc[-d - 1]) - (spy.iloc[-1] / spy.iloc[-d - 1])) * 100, 2)
                       for lab, d in (("1m", 21), ("3m", 63), ("6m", 126)) if len(s) > d}
    return out


FACTORS = {"rates_10y": "bp change in the 10-yr Treasury yield", "oil": "% change in WTI crude",
           "dollar": "% change in the dollar (UUP)", "credit": "% change in HYG/IEF (up = credit spreads tightening)",
           "inflation_exp": "% change in TIP/IEF (up = inflation expectations rising)"}


def sector_sensitivities(px, weeks=156):
    """Per sector ETF: weekly excess return vs SPY explained by weekly factor moves (native units),
    so a forecast move can be translated into an expected sector effect by code, not by story."""
    f = factor_changes(px).tail(weeks)
    w = px.resample("W-FRI").last().pct_change(fill_method=None).tail(weeks) * 100
    out = {}
    if "SPY" not in w or f.empty:
        return out
    for sector, etf in SECTORS.items():
        if etf not in w:
            continue
        d = pd.concat([(w[etf] - w["SPY"]).rename("y"), f], axis=1).dropna()
        if len(d) < 52:
            continue
        cols = [c for c in f.columns if d[c].std() > 0]
        A = np.column_stack([np.ones(len(d))] + [d[c].values for c in cols])
        coef, *_ = np.linalg.lstsq(A, d.y.values, rcond=None)
        resid = d.y.values - A @ coef
        sd_w = float(np.sqrt(resid @ resid / max(1, len(d) - A.shape[1])))
        out[sector] = {"beta": {c: round(float(b), 4) for c, b in zip(cols, coef[1:])}, "sd_4w_%": round(sd_w * 2, 3)}
    return out


OIL_SHOCK_PCT = 20


def oil_shock(sens, move=OIL_SHOCK_PCT):
    """Each sector's expected return vs SPY if oil jumps (or falls) by `move` %, from the measured
    weekly sensitivities: the same numbers code uses to turn an oil forecast into sector effects."""
    out = {}
    for sector, v in (sens or {}).items():
        b = (v.get("beta") or {}).get("oil")
        if b is not None:
            out[sector] = {f"oil_up_{move}%": round(b * move, 2), f"oil_down_{move}%": round(-b * move, 2)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1][f"oil_up_{move}%"]))


def sector_base_rates(hist, k=24):
    """Starting probability per sector: how often it beat SPY over the next month in the same regime,
    pulled toward 50% when there are few such months."""
    out = {}
    for sector, rows in (hist.get("sectors") or {}).items():
        r = rows.get("same_regime_1m") or {}
        n = r.get("n_months", 0) or 0
        beat = r.get("beat_spy_%")
        p = ((beat / 100) * n + 0.5 * k) / (n + k) if beat is not None else 0.5
        out[sector] = {"p": round(p, 4), "n_months": n}
    return out


def momentum_rule(px):
    """The free opponent: favor the sectors with the strongest past-12-month return vs SPY."""
    spy = px["SPY"].dropna()
    ex = {}
    for sector, etf in SECTORS.items():
        s = px[etf].dropna() if etf in px else pd.Series(dtype=float)
        if len(s) > 253 and len(spy) > 253:
            ex[sector] = (s.iloc[-1] / s.iloc[-253]) - (spy.iloc[-1] / spy.iloc[-253])
    ranked = sorted(ex, key=lambda k: -ex[k])
    out = {}
    n = len(ranked)
    for i, sector in enumerate(ranked, 1):
        tilt = 2 if i <= 2 else 1 if i <= 4 else -2 if i > n - 2 else -1 if i > n - 4 else 0
        out[sector] = {"rank": i, "p": round(0.60 - 0.20 * (i - 1) / max(1, n - 1), 4), "tilt": tilt,
                       "excess_12m_%": round(ex[sector] * 100, 1)}
    return out


def market_implied(table):
    """What markets already price for the next 4 weeks. Traded prices (yields, oil, the dollar, credit,
    inflation expectations) are priced to move about zero on average, so the market's expected change is
    0; the Fed path is shown for context (3-month bill vs fed funds)."""
    fed = None
    if "DTB3" in table and "DFF" in table and table["DTB3"].get("latest") is not None:
        fed = round((table["DTB3"]["latest"] - table["DFF"]["latest"]) * 100)
    return {"rates_10y": 0.0, "oil": 0.0, "dollar": 0.0, "credit": 0.0, "inflation_exp": 0.0,
            "fed_funds_3m_implied_bp": fed}


def _norm_ppf(p):
    from statistics import NormalDist
    return NormalDist().inv_cdf(min(max(p, 1e-4), 1 - 1e-4))


def _norm_cdf(x):
    from statistics import NormalDist
    return NormalDist().cdf(x)


def sector_probability(p0, sens, moves, narrative_pts=0.0):
    """P(sector beats SPY over 4 weeks) = base rate shifted by the measured effect of the factor moves
    (expected excess return / its 4-week noise), plus capped narrative points."""
    if not sens:
        return min(0.97, max(0.03, p0 + narrative_pts / 100)), 0.0
    mu = sum(sens["beta"].get(f, 0.0) * (moves.get(f) or 0.0) for f in FACTORS)
    sd = max(sens.get("sd_4w_%") or 1.0, 0.1)
    p = _norm_cdf(_norm_ppf(p0) + mu / sd)
    factor_pts = (p - p0) * 100
    return min(0.97, max(0.03, p + narrative_pts / 100)), round(factor_pts, 2)


def derived(table, raw, px, reg):
    d = {"regime": reg.iloc[-1]["regime"], "fed_direction": reg.iloc[-1].get("fed")}
    gap = round(table["DGS2"]["latest"] - table["DFF"]["latest"], 2)
    d["market_implied_fed_path"] = {"2yr_minus_fed_funds": gap, "reading": (
        "markets price further hikes" if gap > 0.25 else "markets price cuts" if gap < -0.25
        else "markets price roughly no change")}
    if "PCOPPUSDM" in raw and "GC=F" in px:
        ratio = (monthly(raw["PCOPPUSDM"]) / px["GC=F"].resample("ME").mean()).dropna()
        if len(ratio) > 4:
            d["copper_gold_ratio"] = {"latest": round(float(ratio.iloc[-1]), 3), "3m_ago": round(float(ratio.iloc[-4]), 3),
                                      "as_of": ratio.index[-1].date().isoformat()}
        g = px["GC=F"].dropna()
        d["gold"] = {"latest": round(float(g.iloc[-1]), 1), "as_of": g.index[-1].date().isoformat(),
                     "3m_ago": round(float(g.iloc[-64]), 1) if len(g) > 64 else None}
    return d


def release_dates(start, end, with_future):
    params = {"api_key": config.secret("FRED_API_KEY"), "file_type": "json", "realtime_start": start.isoformat(),
              "realtime_end": end.isoformat(), "include_release_dates_with_no_data": "true" if with_future else "false",
              "sort_order": "asc", "limit": 1000}
    try:
        return requests.get("https://api.stlouisfed.org/fred/releases/dates", params=params, timeout=30).json()["release_dates"]
    except Exception:
        return None


def release_calendar():
    keep = ("Employment Situation", "Consumer Price Index", "Personal Income and Outlays", "Gross Domestic Product",
            "Job Openings", "Retail", "Producer Price Index", "Employment Cost Index", "Industrial Production",
            "Senior Loan Officer")
    params = {"api_key": config.secret("FRED_API_KEY"), "file_type": "json", "realtime_start": TODAY.isoformat(),
              "realtime_end": (TODAY + timedelta(days=35)).isoformat(),
              "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 1000}
    try:
        rows = requests.get("https://api.stlouisfed.org/fred/releases/dates", params=params, timeout=30).json()["release_dates"]
    except Exception:
        return []
    seen, out = set(), []
    for r in rows:
        key = (r["date"], r["release_name"])
        if key not in seen and any(k.lower() in r["release_name"].lower() for k in keep):
            seen.add(key)
            out.append({"date": r["date"], "release": r["release_name"]})
    return sorted(out, key=lambda x: x["date"])


def triggers(table, px):
    t = []
    v, h = table.get("VIXCLS"), table.get("BAMLH0A0HYM2")
    if v and v["latest"] and v["latest"] > 35:
        t.append(f"VIX at {v['latest']} (above 35)")
    if h and h["latest"] and h["3m_ago"] and h["latest"] - h["3m_ago"] > 1.5:
        t.append(f"High-yield spread up {h['latest'] - h['3m_ago']:.2f} pts in 3 months")
    spy = px["SPY"].dropna()
    if len(spy) > 6 and spy.iloc[-1] / spy.iloc[-6] - 1 < -0.07:
        t.append(f"S&P 500 down {(spy.iloc[-1] / spy.iloc[-6] - 1) * 100:.1f}% in a week")
    return t


# ==================================================================== 3. EVIDENCE
def gather(session, ck=None, only=None):
    system = ("You are a research assistant gathering facts for a macro investment committee. Report only what "
              "the sources state, with numbers exactly as written and the date they refer to. If you cannot "
              "find something, write NOT FOUND. Never estimate. " + JSON_RULE)
    notes, dropped = [], []
    for key, (name, asks) in THEMES.items():
        if only is not None and key not in only:
            continue
        if ck and ck.has_item("gather", key):
            saved = ck.item("gather", key)
            notes += saved["notes"]
            dropped += saved["dropped"]
            continue
        prompt = f"""Today is {TODAY}. Theme: {name}. Find:
{asks}
JSON: [{{"id": "{key}1", "topic": "...", "finding": "one sentence", "value": "key number as written, or null",
  "as_of": "YYYY-MM-DD or month", "url": "exact source URL"}}]"""
        r = session.ask("macro_gather", system, prompt, max_tokens=4000,
                        search={"max_uses": SEARCHES_PER_THEME, "allowed": config.MACRO_ALLOWED_DOMAINS})
        k, d = validate_notes(r.data if isinstance(r.data, list) else [], r.receipts, "allow")
        notes += k
        dropped += d
        if ck:
            ck.save_item("gather", key, {"notes": k, "dropped": d})
    return notes, dropped


# ==================================================================== 4. REASONING
def merge_events(runs):
    """Every reasoner's dated events, one row per (date, event), soonest first."""
    seen, out = set(), []
    for r in runs:
        for e in r.get("upcoming_events") or []:
            if isinstance(e, dict) and str(e.get("date", ""))[:4].isdigit() and e.get("event"):
                k = (str(e["date"])[:10], str(e["event"]).strip().lower()[:60])
                if k not in seen:
                    seen.add(k)
                    out.append({"date": str(e["date"])[:10], "event": e["event"], "exposed": e.get("exposed") or []})
    return sorted(out, key=lambda e: e["date"])


REASON_SYSTEM = """You are a macro strategist for a U.S. stock portfolio with a 1-3 month horizon. You forecast
the ECONOMY and MARKETS; code translates your forecast into sector effects using measured sensitivities.
Rules:
- The packet is a set of tables. EVERY claim cites evidence refs, as objects {"ref": ..., "value": ...}:
  "FRED:<id>" (include the exact number you used), "FACT:<id>" (dot-plot medians etc.),
  "NOTE:<id>", "CALC:<name>", "HIST:<sector>", "MOM:<sector>", "SENS:<sector>". No outside facts or numbers.
- The FRED table is authoritative. Address every CORE variable.
- CALC:recession_risk and CALC:pullback_risk are statistical models (probabilities with their typical
  rates and out-of-sample accuracy); CALC:risk_indicators are the readings behind them. Address both in
  your regime assessment and key risks: agree or explain, with evidence, why the models miss something.
- FACTOR VIEW: forecast the change over the next 4 weeks in: rates_10y (basis points), oil (%), dollar (%),
  credit (% change in HYG/IEF; up = spreads tightening), inflation_exp (% change in TIP/IEF). Markets price
  about ZERO change in these on average, so any non-zero forecast is a bet against the market: make one
  only with cited evidence, otherwise forecast 0. Uncited factor forecasts are set to 0.
- SECTOR ADJUSTMENTS: only for effects the factors can't capture (a tariff on one industry, a regulation,
  a sector-specific data point), at most +/-5 points per sector, each cited. Argue the strongest case
  AGAINST each; if it doesn't survive, drop it.
- GEOPOLITICS (theme E notes, CALC:risk_indicators, the oil-shock table): express its effect through the
  oil factor forecast and, where an industry is directly hit (export controls on chips, sanctions,
  shipping), a cited sector adjustment. Markets price known events within hours: only a view on what
  happens NEXT (escalation, de-escalation, supply actually lost vs threatened) is a forecast. Threats move
  markets more than completed events; don't double count what today's oil price already shows.
- The previous view is in the packet: any change must name the new evidence that justified it.
- UPCOMING EVENTS: list scheduled events in the next 8 weeks that could move a sector or theme sharply either
  way (elections, Fed meetings, major policy votes or deadlines, tariff dates, big data releases), each with
  its date, what is at stake and which sectors or themes are exposed. Cite a NOTE ref where one exists.
  Name the binary ones in key_risks too.
""" + JSON_RULE

REASON_SHAPE = """{
 "regime": {"code_regime_agrees": true, "assessment": "...", "evidence": [{"ref": "...", "value": null}]},
 "core_review": [{"variable": "<FRED id or topic>", "reading": "...", "consensus": "...",
                  "view_vs_consensus": "above|in line|below|n/a", "evidence": [{"ref": "...", "value": null}]}],
 "factor_view": {"rates_10y": {"change": 0, "why": "...", "evidence": [{"ref": "...", "value": null}]},
                 "oil": {"change": 0, "why": "...", "evidence": []}, "dollar": {"change": 0, "why": "...", "evidence": []},
                 "credit": {"change": 0, "why": "...", "evidence": []}, "inflation_exp": {"change": 0, "why": "...", "evidence": []}},
 "scenarios": [{"name": "base|upside|downside", "probability": 0.0, "description": "..."}],
 "sectors": {"<sector>": {"adjustments": [{"points": 0, "reason": "...", "evidence": [{"ref": "...", "value": null}]}],
             "rationale": "...", "counterargument": "...", "survives": true, "change_note": "..."}},
 "key_risks": ["..."],
 "upcoming_events": [{"date": "YYYY-MM-DD", "event": "...", "exposed": ["<sector or theme>"], "evidence": [{"ref": "...", "value": null}]}],
 "predictions": [{"type": "sector_vs_spy", "etf": "XLE", "direction": "outperform|underperform", "weeks": 4},
                 {"type": "fred_threshold", "series": "<FRED id>", "comparison": ">=|<=", "value": 0.0,
                  "check_after": "YYYY-MM-DD"}]
}"""


def reason(session, packet_text, ck=None):
    prompt = (f"Today is {TODAY}. Sectors: {list(SECTORS)}.\nUsing ONLY the packet above, give your view. "
              f"Include 2-4 predictions checkable within 4-8 weeks.\nJSON shape:\n{REASON_SHAPE}")
    reqs = [{"id": f"reason{i}", "role": f"macro_reason_{i}", "system": REASON_SYSTEM, "prompt": prompt,
             "shared": "PACKET:\n" + packet_text, "max_tokens": 8000, "thinking": "medium"} for i in (1, 2, 3, 4)]
    results = session.batch(reqs, checkpoint=ck, key="reason")
    runs = []
    for rid, r in sorted(results.items()):
        if isinstance(r.data, dict) and isinstance(r.data.get("sectors") or r.data.get("tilts"), dict):
            d = dict(r.data, model=r.model + (" (fallback)" if r.fallback else ""))
            d["tilts"] = d.pop("sectors", None) or d.get("tilts")      # per-sector entries (name kept for reports)
            runs.append(d)
        else:
            print(f"  ! {rid} ({r.model}) returned no usable view")
    if len(runs) < 2:
        raise RuntimeError("Fewer than two reasoning runs produced a usable view.")
    return runs


# ==================================================================== 5. REVIEW
def audit_runs(runs, auditor):
    """Strip uncited or wrong evidence. A factor forecast without valid evidence becomes 0 (the market's
    view); a sector adjustment without valid evidence is dropped; each sector is capped at +/-5 points."""
    log = []
    cap = config.MACRO_TILT["narrative_cap"]
    for run in runs:
        fv = run.get("factor_view") if isinstance(run.get("factor_view"), dict) else {}
        clean = {}
        for f in FACTORS:
            x = fv.get(f) if isinstance(fv.get(f), dict) else {}
            try:
                ch = float(x.get("change", 0) or 0)
            except (TypeError, ValueError):
                ch = 0.0
            good, problems = auditor.filter(x.get("evidence"))
            log += [{"model": run["model"], "sector": f"factor {f}", "problem": pr} for pr in problems]
            if ch and not good:
                log.append({"model": run["model"], "sector": f"factor {f}", "problem": "no valid evidence, forecast set to 0"})
                ch = 0.0
            clean[f] = {"change": ch, "why": x.get("why", ""), "evidence": good}
        run["factor_view"] = clean
        for sector in list(run["tilts"]):
            t = run["tilts"][sector]
            if sector not in SECTORS or not isinstance(t, dict):
                run["tilts"].pop(sector)
                continue
            kept, ev = [], []
            for adj in t.get("adjustments") or []:
                if not isinstance(adj, dict):
                    continue
                good, problems = auditor.filter(adj.get("evidence"))
                log += [{"model": run["model"], "sector": sector, "problem": pr} for pr in problems]
                try:
                    pts = float(adj.get("points", 0) or 0)
                except (TypeError, ValueError):
                    pts = 0.0
                if pts and not good:
                    log.append({"model": run["model"], "sector": sector, "problem": "adjustment without valid evidence dropped"})
                    continue
                kept.append({"points": pts, "reason": adj.get("reason", ""), "evidence": good})
                ev += good
            pts = sum(a["points"] for a in kept)
            if t.get("survives") is False:
                pts /= 2
            t["adjustments"], t["evidence"] = kept, ev
            t["points"] = max(-cap, min(cap, pts))
            t["tilt"] = int(max(-2, min(2, round(t["points"] / 2.5))))     # display only
        for c in run.get("core_review", []) if isinstance(run.get("core_review"), list) else []:
            c["evidence"], probs = auditor.filter(c.get("evidence"), for_score=False)
            log += [{"model": run["model"], "sector": "core review", "problem": p} for p in probs]
    return log


def tilt_for(d_pts, prev=0):
    """Disagreement with market pricing (points) -> tilt. Small (2+ pts) -> +/-1, large (5+) -> +/-2.
    Changing an existing tilt needs the new level's boundary cleared by a 1-point buffer, so tilts don't
    flip month to month on noise."""
    T = config.MACRO_TILT
    L1, L2, h = T["small"], T["full"], T["hysteresis"]
    inf = float("inf")
    lower = {-2: -inf, -1: -L2, 0: -L1, 1: L1, 2: L2}
    upper = {-2: -L2, -1: -L1, 0: L1, 1: L2, 2: inf}
    target = next(k for k in (2, 1, 0, -1, -2) if d_pts >= lower[k])
    if target == prev:
        return prev
    if target > prev:
        for k in range(target, prev, -1):
            if d_pts >= lower[k] + h:
                return k
        return prev
    for k in range(target, prev):
        if d_pts <= upper[k] - h:
            return k
    return prev


def combine(runs, last, packet=None):
    """Median factor forecast and median sector adjustments across the models -> sector probabilities
    -> tilts from the part that disagrees with market pricing (at most two full tilts)."""
    packet = packet or {}
    sens = packet.get("sector_sensitivities") or {}
    base = packet.get("sector_base_rates") or {}
    market = packet.get("market_implied") or {}
    moves = {f: float(np.median([r["factor_view"].get(f, {}).get("change", 0.0) for r in runs])) for f in FACTORS}
    mkt = {f: float(market.get(f) or 0.0) for f in FACTORS}
    final = {}
    for sector in SECTORS:
        pts = [r["tilts"].get(sector, {}).get("points", 0.0) for r in runs]
        narrative = float(np.median(pts)) if pts else 0.0
        p0 = (base.get(sector) or {}).get("p", 0.5)
        p, factor_pts = sector_probability(p0, sens.get(sector), moves, narrative)
        p_mkt, _ = sector_probability(p0, sens.get(sector), mkt, 0.0)
        d = round((p - p_mkt) * 100, 2)
        prev = (last or {}).get("tilts", {}).get(sector, 0) or 0
        final[sector] = {"p": round(p, 4), "base_p": round(p0, 4), "p_market": round(p_mkt, 4), "disagreement_pts": d,
                         "factor_pts": factor_pts, "narrative_pts": round(narrative, 2), "tilt": tilt_for(d, prev),
                         "note": f"base {p0:.0%}, factors {factor_pts:+.1f}, sector-specific {narrative:+.1f} "
                                 f"(models {pts}) -> {p:.0%}; vs market pricing {d:+.1f} pts"}
    full = sorted([s for s, v in final.items() if abs(v["tilt"]) == 2], key=lambda s: -abs(final[s]["disagreement_pts"]))
    for s in full[config.MACRO_TILT["max_full"]:]:
        final[s]["tilt"] = int(np.sign(final[s]["tilt"]))
        final[s]["note"] += "; capped at +/-1 (only two full tilts allowed)"
    set_ranges(final)
    return final, moves


def set_ranges(final):
    """Weight range per sector from its tilt, scaled so the ranges can always sum to 100%."""
    r = config.ranges_for({s: v["tilt"] for s, v in final.items()})
    for s, v in final.items():
        v["range_%"] = r[s]
    return final


def apply_critic_flags(final, crit):
    """A sector the critic FLAGs moves one step toward neutral (e.g. -2 -> -1). Returns the sectors changed."""
    moved = []
    for s, c in ((crit or {}).get("sectors") or {}).items():
        if s in final and (c or {}).get("status") == "FLAG" and final[s]["tilt"]:
            old = final[s]["tilt"]
            final[s]["tilt"] = old - int(np.sign(old))
            final[s]["note"] += f"; critic flagged it ({str(c.get('issue', ''))[:120]}): tilt {old:+d} -> {final[s]['tilt']:+d}"
            moved.append(s)
    if moved:
        set_ranges(final)
    return moved


def etf_weights(tilts):
    """Sector-ETF portfolio for a set of tilts (equal weight, +/-50% per tilt step)."""
    raw = {SECTORS[s]: max(0.0, 1 + 0.5 * t) for s, t in tilts.items() if s in SECTORS}
    tot = sum(raw.values()) or 1
    return {k: round(v / tot * 100, 2) for k, v in raw.items() if v > 0}


def critic(session, final, runs, packet_text, ck=None):
    if ck and ck.has("critic"):
        return ck.get("critic")
    summary = {s: {"final_tilt": final[s]["tilt"], "how": final[s]["note"],
                   "arguments": [{"model": r["model"], **{k: r["tilts"].get(s, {}).get(k) for k in
                                  ("points", "adjustments", "rationale", "counterargument", "survives")}} for r in runs]}
               for s in SECTORS}
    summary["_factor_views"] = [{"model": r["model"], "factor_view": r.get("factor_view")} for r in runs]
    system = ("You are the logic reviewer on an investment committee. For each sector tilt: does it follow from "
              "its cited evidence? Look for contradictions, double counting, stale data, and counter-evidence in "
              "the packet that was ignored. FAIL only a tilt that is clearly unsupported or contradicted. " + JSON_RULE)
    prompt = (f"TILTS TO REVIEW:\n{json.dumps(summary, default=str)}\n"
              'JSON: {"overall": "PASS|FLAG|FAIL", "summary": "...", '
              '"sectors": {"<sector>": {"status": "PASS|FLAG|FAIL", "issue": "..."}}}')
    r = session.ask("macro_critic", system, prompt, shared="PACKET:\n" + packet_text, max_tokens=12000)   # 4000 truncated its review
    out = r.data if isinstance(r.data, dict) else {"overall": "FLAG", "summary": "critic reply unusable", "sectors": {}}
    return ck.save("critic", out) if ck else out


# ==================================================================== predictions
def grade_predictions(px, raw):
    path = state_path("macro_predictions.csv")
    if not path.exists():
        return {"graded": 0}
    p = pd.read_csv(path, dtype=str)
    for i, r in p[p.status == "pending"].iterrows():
        d, made = json.loads(r.detail), pd.Timestamp(r.made)
        if d.get("type") == "sector_vs_spy" and d.get("etf") in px:
            due = made + pd.Timedelta(weeks=int(d.get("weeks", 4)))
            s, spy = px[d["etf"]].dropna(), px["SPY"].dropna()
            if s.empty or s.index[-1] < due or s[s.index >= made].empty:
                continue
            ex = (s[s.index <= due].iloc[-1] / s[s.index >= made].iloc[0] - 1) - \
                 (spy[spy.index <= due].iloc[-1] / spy[spy.index >= made].iloc[0] - 1)
            hit = ex > 0 if d.get("direction") == "outperform" else ex < 0
            p.loc[i, ["status", "result"]] = ["hit" if hit else "miss", f"excess {ex * 100:+.2f}%"]
        elif d.get("type") == "fred_threshold":
            row = next((x for x in FRED if x[0] == d.get("series")), None)
            if not row or row[0] not in raw or pd.Timestamp(TODAY) < pd.Timestamp(d.get("check_after", "2100-01-01")):
                continue
            v = transform(raw[row[0]], row[3]).dropna()
            v = v[v.index > made]
            if v.empty:
                continue
            val = float(v.iloc[0])
            hit = val >= float(d["value"]) if d.get("comparison") == ">=" else val <= float(d["value"])
            p.loc[i, ["status", "result"]] = ["hit" if hit else "miss", f"actual {val:.2f}"]
    p.to_csv(path, index=False)
    done = p[p.status.isin(["hit", "miss"])]
    return {"graded": len(done), "hits": int((done.status == "hit").sum()),
            "hit_rate_%": round(float((done.status == "hit").mean() * 100), 1) if len(done) else None,
            "by_model": {m: f"{int((g.status == 'hit').sum())}/{len(g)}" for m, g in done.groupby("model")}}


def log_predictions(runs):
    rows = [{"made": TODAY.isoformat(), "model": r["model"], "detail": json.dumps(pr), "status": "pending", "result": ""}
            for r in runs for pr in (r.get("predictions") or [])
            if isinstance(pr, dict) and pr.get("type") in ("sector_vs_spy", "fred_threshold")]
    append_csv(state_path("macro_predictions.csv"), rows)


# ==================================================================== 6. OUTPUT
def ref_text(ev, fred, notes, facts):
    ref = ev.get("ref", "") if isinstance(ev, dict) else str(ev)
    kind, _, key = ref.partition(":")
    if kind == "FRED" and key in fred:
        r = fred[key]
        return f"{r['label']} = {r['latest']} (FRED {key}, as of {r['as_of']})"
    if kind == "FACT" and key in facts:
        return f"{key} = {facts[key]} (FRED Fed projections)"
    if kind == "NOTE" and key in notes:
        n = notes[key]
        warn = " ⚠️ number not found in source text" if n.get("verified_number") is False else ""
        return f"{n.get('finding')} ({n.get('as_of', '')}) {n.get('url')}{warn}"
    return ref


def report(final, runs, crit, audit_log, packet, notes, dropped, missing, status, usage_so_far):
    fred, facts = packet["fred"], packet["facts"]
    nmap = {n["id"]: n for n in notes}
    L = [f"# Macro view, {TODAY}", f"**Status: {status}**", ""]
    if packet.get("why_this_run"):
        L += ["Why this run: " + "; ".join(packet["why_this_run"]), ""]
    if packet["triggers"]:
        L += ["## ⚠️ Off-cycle triggers"] + [f"- {t}" for t in packet["triggers"]] + [""]
    L += ["## Regime", f"Code: **{packet['calc']['regime']}**, Fed {packet['calc']['fed_direction']}", ""]
    L += market_risk.report_md(packet.get("market_risk"))
    if packet.get("oil_shock"):
        L += [f"## Oil shock: sector return vs SPY if oil moves {OIL_SHOCK_PCT}%", "| Sector | Oil up | Oil down |", "|---|---|---|"]
        L += [f"| {sec} | {v[f'oil_up_{OIL_SHOCK_PCT}%']:+.1f}% | {v[f'oil_down_{OIL_SHOCK_PCT}%']:+.1f}% |"
              for sec, v in packet["oil_shock"].items()] + [""]
    L += [f"- *{r['model']}*: {(r.get('regime') or {}).get('assessment', '')}" for r in runs]
    fv = packet.get("factor_view_combined") or {}
    L += ["", "## Economic forecast (median of the models, next 4 weeks)"] + [f"- {FACTORS[f]}: {fv.get(f, 0):+g}" for f in FACTORS]
    L += ["", "## Sector probabilities and tilts",
          "| Sector | P(beat SPY) | Base rate | vs market pricing | Tilt | Weight range | Momentum rule | Critic | How decided |",
          "|---|---|---|---|---|---|---|---|---|"]
    mom = packet.get("momentum_rule") or {}
    for s, v in final.items():
        c = (crit.get("sectors") or {}).get(s, {})
        L.append(f"| {s} | {v.get('p', 0.5):.0%} | {v.get('base_p', 0.5):.0%} | {v.get('disagreement_pts', 0):+.1f} | {v['tilt']:+d} | "
                 f"{v['range_%'][0]}–{v['range_%'][1]}% | {(mom.get(s) or {}).get('tilt', '')} | {c.get('status', '')} | {v['note']} |")
    L += ["", f"Critic: **{crit.get('overall')}**. {crit.get('summary', '')}", ""]
    for s in SECTORS:
        L.append(f"### {s}")
        for r in runs:
            t = r["tilts"].get(s)
            if t:
                L += [f"**{r['model']}** ({t.get('points', 0):+.1f} pts): {t.get('rationale', '')}",
                      f"- against: {t.get('counterargument', '')} (survives: {t.get('survives')})"]
                L += [f"  - 📎 {ref_text(e, fred, nmap, facts)}" for e in t.get("evidence", [])]
        c = (crit.get("sectors") or {}).get(s)
        if c and c.get("status") != "PASS":
            L.append(f"- 🔎 Critic {c.get('status')}: {c.get('issue')}")
        L.append("")
    L.append("## Core variables vs consensus")
    for r in runs[:1]:
        for c in r.get("core_review") or []:
            cites = "; ".join(ref_text(e, fred, nmap, facts) for e in c.get("evidence", []))
            L.append(f"- **{c.get('variable')}**: {c.get('reading')} | consensus: {c.get('consensus')} | "
                     f"view: {c.get('view_vs_consensus')}  \n  📎 {cites}")
    L += ["", "## Scenarios"] + [f"*{r['model']}*: " + "; ".join(
        f"{x.get('name')} ({x.get('probability')}): {x.get('description')}" for x in r.get("scenarios") or [] if isinstance(x, dict))
        for r in runs]
    L += ["", "## Upcoming releases"] + [f"- {c['date']}: {c['release']}" for c in packet["calendar"]]
    L += ["", "## Prediction scorecard", json.dumps(packet["prediction_scorecard"]), "", "## Data quality"]
    L += [f"- {r['label']}: {', '.join(r['flags'])}" for r in fred.values() if r["flags"]]
    L += [f"- MISSING {m['label']} ({m['id']})" for m in missing]
    L += [f"- Auditor removed ({a['model']}, {a['sector']}): {a['problem']}" for a in audit_log]
    L += [f"- Dropped note: {d.get('finding')} ({d.get('url')}): {d.get('reason')}" for d in dropped]
    L += ["", "## Evidence notes"] + [f"- NOTE:{n['id']} {n.get('finding')} ({n.get('url')})" for n in notes]
    if packet.get("sources"):
        L += ["", "## Direct-fetch sources (fix URLs in pipeline/fetch.py if one keeps failing)"]
        L += [f"- {x['theme']} {x['source']}: {x['status']} ({x['url']})" for x in packet["sources"]]
    L += ["", f"_Model cost so far ≈ ${usage_so_far:.2f}. Full receipts in sources.csv and full_run.json._"]
    return "\n".join(L)


def email(final, status, crit, packet, report_path, cost):
    rows = "".join(f"<tr><td>{s}</td><td>{v.get('p', 0.5):.0%}</td><td>{v.get('disagreement_pts', 0):+.1f}</td>"
                   f"<td style='text-align:center'><b>{v['tilt']:+d}</b></td>"
                   f"<td>{v['range_%'][0]}–{v['range_%'][1]}%</td><td>{v['note']}</td></tr>" for s, v in final.items())
    trig = "".join(f"<li>{t}</li>" for t in packet["triggers"])
    why = "".join(f"<li>{w}</li>" for w in packet.get("why_this_run", []))
    review = packet.get("review_url")
    html = (f"<h3>Macro view, {TODAY}: {status}</h3>"
            + (f"<p><b>⚠️ On hold for your review:</b> tick APPROVE or REJECT at {review}. Until then the "
               f"previous view stays in use.</p>" if review else "")
            + (f"<p><b>Why this run:</b></p><ul>{why}</ul>" if why else "")
            + f"<p><b>Regime:</b> {packet['calc']['regime']} · Fed {packet['calc']['fed_direction']}</p>"
            + (f"<p><b>Risk:</b> {(packet.get('market_risk') or {}).get('summary')}</p>"
               if (packet.get("market_risk") or {}).get("summary") else "")
            + (f"<p><b>⚠️ Triggers:</b></p><ul>{trig}</ul>" if trig else "")
            + f"<table border='1' cellpadding='4' style='border-collapse:collapse'><tr><th>Sector</th><th>P(beat SPY)</th>"
              f"<th>vs market pts</th><th>Tilt</th><th>Range</th><th>How decided</th></tr>{rows}</table>"
            f"<p><b>Critic:</b> {crit.get('overall')}. {crit.get('summary', '')}</p><p>Run cost ≈ ${cost:.2f}. "
            f"Full report attached.</p>")
    text = "\n".join(f"{s}: {v['tilt']:+d} ({v['range_%'][0]}-{v['range_%'][1]}%)" for s, v in final.items())
    headline = "; ".join(f"{s} {v['tilt']:+d}" for s, v in final.items() if v["tilt"]) or "all neutral"
    send(subject_line("Macro", status, headline), text, html, attachments=[report_path],
         save_dir=report_path.parent)


# ==================================================================== light check, tripwires, schedule
def tripwires(fred, facts, trig, baseline):
    """Code-only reasons to run the full (paid) macro agent before its monthly slot."""
    w = list(trig)
    if not baseline:
        return w
    bf = baseline.get("fred", {})
    for sid, row in fred.items():
        if row["tier"] != "core":
            continue
        b = bf.get(sid) or {}
        z, bz = row.get("z_5yr"), b.get("z")
        if z is None or bz is None:
            continue
        if abs(z) >= 2 > abs(bz):
            w.append(f"{row['label']} is newly unusual (z {bz:+.1f} -> {z:+.1f})")
        elif abs(z - bz) >= 1.0:
            w.append(f"{row['label']} moved {z - bz:+.1f} standard deviations since the last full run "
                     f"({b.get('latest')} -> {row['latest']})")
    if "DFF" in fred and baseline.get("dff") is not None and abs(fred["DFF"]["latest"] - baseline["dff"]) >= 0.2:
        w.append(f"Fed funds rate changed ({baseline['dff']} -> {fred['DFF']['latest']})")
    bfacts = baseline.get("facts", {})
    if any(k in bfacts and abs(v - bfacts[k]) > 1e-9 for k, v in facts.items()) or \
            (bfacts and set(facts) - set(bfacts)):
        w.append("New Fed projections (dot plot) since the last full run")
    return w


def full_run_due(baseline, view):
    """Monthly schedule: once both this month's jobs report and CPI are out."""
    if not view or not baseline:
        return "no macro view yet"
    last = date.fromisoformat(baseline["date"])
    if (TODAY - last).days > 35:
        return "more than 5 weeks since the last full run"
    rows = release_dates(TODAY.replace(day=1), TODAY, with_future=False)
    if rows is None:     # FRED calendar unavailable: fall back to "mid-month, not yet run this month"
        return "monthly run (mid-month)" if TODAY.day >= 15 and (last.year, last.month) != (TODAY.year, TODAY.month) else None
    jobs = [r["date"] for r in rows if "Employment Situation" in r["release_name"] and r["date"] <= TODAY.isoformat()]
    cpi = [r["date"] for r in rows if r["release_name"].startswith("Consumer Price Index") and r["date"] <= TODAY.isoformat()]
    if jobs and cpi and last.isoformat() < max(max(jobs), max(cpi)):
        return f"monthly run: this month's jobs report ({max(jobs)}) and CPI ({max(cpi)}) are both out"
    return None


def what_changed(fred, baseline):
    """Digest of moves since the last full run, for the in-between rebuilds (free, code-only)."""
    if not baseline:
        return []
    rows = []
    for sid, row in fred.items():
        b = baseline.get("fred", {}).get(sid)
        if not b or (row["tier"] == "watch" and not row["flags"]):
            continue
        dz = round(row["z_5yr"] - b["z"], 2) if row.get("z_5yr") is not None and b.get("z") is not None else None
        rows.append({"id": sid, "label": row["label"], "tier": row["tier"], "at_view": b.get("latest"),
                     "now": row["latest"], "as_of": row["as_of"], "z_change": dz, "flags": row["flags"]})
    return sorted(rows, key=lambda r: -abs(r["z_change"] or 0))


def save_baseline(fred, facts):
    write_json(state_path("macro_baseline.json"), {
        "date": TODAY.isoformat(), "facts": facts, "dff": (fred.get("DFF") or {}).get("latest"),
        "fred": {sid: {"latest": r["latest"], "z": r.get("z_5yr")} for sid, r in fred.items()}})


# ==================================================================== compact tables for the models
def _cell(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v).replace("|", "/")


def render_packet(p):
    """The packet as compact tables: same fields and numbers as before, column names written once."""
    L = [f"DATE {p['today']}"]
    if p.get("why_this_run"):
        L += ["", "## WHY THIS RUN"] + [f"- {w}" for w in p["why_this_run"]]
    L += ["", "## FRED DATA (authoritative; cite FRED:<id> with the exact value). tier: core = must address, "
              "driver = justifies sector tilts, watch = mention only if unusual or central",
          "id | label | tier | latest | as_of | 3m_ago | 12m_ago | 3m_direction | z_5yr | percentile_5yr | flags"]
    for r in p["fred"].values():
        L.append(" | ".join(_cell(r.get(k)) for k in ("id", "label", "tier", "latest", "as_of", "3m_ago", "12m_ago",
                                                      "direction_3m", "z_5yr", "percentile_5yr")) + " | " + "; ".join(r["flags"]))
    L += ["", "## FED PROJECTIONS: dot-plot medians by year (cite FACT:<id>)", "id | value"]
    L += [f"{k} | {_cell(v)}" for k, v in p["facts"].items()]
    L += ["", "## CALCULATIONS (cite CALC:<name>)", "name | value"]
    for k, v in p["calc"].items():
        L.append(f"{k} | " + ("; ".join(f"{a}={_cell(b)}" for a, b in v.items()) if isinstance(v, dict) else _cell(v)))
    if p.get("triggers"):
        L += ["", "## EMERGENCY TRIGGERS"] + [f"- {t}" for t in p["triggers"]]
    h = p["history_by_regime"]
    L += ["", f"## SECTOR HISTORY in months like now (regime: {h['current_regime']}; Fed {h['current_fed']}); sector ETF "
              "return vs SPY over the following 1 or 3 months (cite HIST:<sector>)",
          "sector | window | avg_excess_% | beat_spy_% | n_months"]
    for sec, rows in h["sectors"].items():
        for k, v in rows.items():
            L.append(f"{sec} | {k} | {_cell(v.get('avg_excess_%'))} | {_cell(v.get('beat_spy_%'))} | {v.get('n_months')}")
    L += ["", "## SECTOR SENSITIVITIES (cite SENS:<sector>): weekly sector return minus SPY per unit weekly factor move "
              "(rates_10y per bp; others per %), last 3 years; code uses these to turn your factor forecast into sector effects",
          "sector | " + " | ".join(FACTORS) + " | 4-week noise %"]
    for sec, v in (p.get("sector_sensitivities") or {}).items():
        L.append(f"{sec} | " + " | ".join(_cell(v["beta"].get(f)) for f in FACTORS) + f" | {_cell(v.get('sd_4w_%'))}")
    if p.get("oil_shock"):
        L += ["", f"## OIL SHOCK: expected sector return vs SPY (%) if oil moves {OIL_SHOCK_PCT}% (from SENS:<sector>)",
              f"sector | oil +{OIL_SHOCK_PCT}% | oil -{OIL_SHOCK_PCT}%"]
        L += [f"{sec} | {v[f'oil_up_{OIL_SHOCK_PCT}%']:+.2f} | {v[f'oil_down_{OIL_SHOCK_PCT}%']:+.2f}" for sec, v in p["oil_shock"].items()]
    L += ["", "## STARTING PROBABILITIES: P(sector beats SPY next month) in months like now, pulled toward 50% when rare",
          "sector | p | n_months"]
    L += [f"{sec} | {_cell(v['p'])} | {v['n_months']}" for sec, v in (p.get("sector_base_rates") or {}).items()]
    mi = p.get("market_implied") or {}
    L += ["", "## WHAT MARKETS PRICE for the next 4 weeks: about zero change in yields, oil, the dollar, credit and "
              f"inflation expectations; Fed: 3-month bill minus fed funds = {mi.get('fed_funds_3m_implied_bp')} bp"]
    L += ["", "## SECTOR MOMENTUM: ETF return minus SPY, % (cite MOM:<sector>)", "sector | 1m | 3m | 6m"]
    for sec, m in p["momentum"].items():
        L.append(f"{sec} | " + " | ".join(_cell(m.get(f"excess_vs_spy_{w}_%")) for w in ("1m", "3m", "6m")))
    L += ["", "## EVIDENCE NOTES: verified against their sources (cite NOTE:<id>)", "id | finding | value | as_of | source"]
    for n in p.get("notes", []):
        flag = " (number not confirmed in source)" if n.get("verified_number") is False else ""
        L.append(f"{n['id']} | {_cell(n.get('finding'))}{flag} | {_cell(n.get('value'))} | {_cell(n.get('as_of'))} | {_cell(n.get('url'))}")
    L += ["", "## UPCOMING RELEASES"] + [f"- {c['date']}: {c['release']}" for c in p.get("calendar", [])]
    pv = p.get("previous_view")
    L += ["", "## PREVIOUS VIEW"] + ([f"date {pv['date']}: " + ", ".join(f"{s} {t:+d}" for s, t in (pv.get("tilts") or {}).items())]
                                    if pv else ["none"])
    L += ["", "## PREDICTION SCORECARD", json.dumps(p.get("prediction_scorecard"))]
    if p.get("missing_data"):
        L += ["", "## MISSING DATA (unavailable this run)"] + [f"- {m}" for m in p["missing_data"]]
    return "\n".join(L)


# ==================================================================== MAIN
def main(session, folder, mode=None):
    mode = mode or ("full" if "--full" in sys.argv else "auto")
    check_macro()                                  # apply your APPROVE/REJECT on a held view first
    view = read_json(state_path("macro_view.json"))
    baseline = read_json(state_path("macro_baseline.json"))
    pending = cpt.incomplete("macro")
    if pending and (pending.get("steps") or {}).get("packet"):
        ck = Checkpoint("macro")
        print(f"Resuming the full macro run started {ck.data['started']} (attempt {ck.attempts})")
        packet, missing, dropped = ck.get("packet"), ck.get("missing", []), ck.get("dropped", [])
    else:
        print("1/6 Light check: FRED data, Fed projections, market data...")
        fred, raw, missing = load_fred()
        sep, facts = load_sep()
        px = market_data()
        reg = regime_series(raw)
        calc = derived(fred, raw, px, reg)
        print("    Market & recession risk models...")
        prev_risk = read_json(state_path("market_risk.json"))
        try:
            risk = market_risk.compute(fred_obs)
        except Exception as e:                      # never blocks the macro run
            risk = {"date": TODAY.isoformat(), "error": str(e)[:200]}
        market_risk.save(risk)
        print("    " + (risk.get("summary") or f"unavailable: {risk.get('error')}"))
        calc.update(market_risk.calc_entries(risk))
        trig = triggers(fred, px)
        wires = tripwires(fred, facts, trig, baseline)
        rw = market_risk.tripwire(risk, prev_risk)
        if rw:
            wires.append(rw)
        due = full_run_due(baseline, view)
        write_json(state_path("macro_check.json"), {
            "date": TODAY.isoformat(), "view_date": (view or {}).get("date"), "regime": calc["regime"],
            "fed": calc["fed_direction"], "triggers": trig, "tripwires": wires,
            "market_risk": risk.get("summary") or risk.get("error"),
            "changes_since_view": what_changed(fred, baseline), "missing": [m["label"] for m in missing]})
        why = (["forced (--full)"] if mode == "full" else []) + ([due] if due else []) + [f"tripwire: {w}" for w in wires]
        if pending:
            why.insert(0, "resuming a stopped full run")
        print(f"    {len(fred)} series; regime {calc['regime']}; Fed {calc['fed_direction']}")
        if not why:
            print("    Light check only: nothing tripped and the monthly run isn't due. No AI calls, no email.")
            return {"status": "light check"}
        if config.MACRO_MODE == "neutral":
            print("    MACRO_MODE=neutral: no tilts and no paid run (pruned by the 12-month rule).")
            if not view or any(view.get("tilts", {}).values()) or not view.get("neutral_mode"):
                write_json(state_path("macro_view.json"), {
                    "date": TODAY.isoformat(), "status": "OK", "regime": calc["regime"], "fed": calc["fed_direction"],
                    "tilts": {s: 0 for s in SECTORS}, "weight_ranges_%": {s: list(config.TILT_RANGES[0]) for s in SECTORS},
                    "triggers": trig, "why": ["MACRO_MODE=neutral"], "key_risks": [], "neutral_mode": True})
            return {"status": "neutral mode"}
        print("    Full run because: " + "; ".join(why))
        ck = Checkpoint("macro")
        packet = {"today": TODAY.isoformat(), "why_this_run": why, "fred": fred, "fed_projections_dot_plot": sep,
                  "facts": facts, "calc": calc, "history_by_regime": history_by_regime(reg, px),
                  "momentum": momentum(px), "calendar": release_calendar(), "triggers": trig,
                  "sector_sensitivities": (sens := sector_sensitivities(px)), "oil_shock": oil_shock(sens),
                  "market_implied": market_implied(fred),
                  "momentum_rule": momentum_rule(px),
                  "previous_view": view and {"date": view.get("date"), "tilts": view.get("tilts")},
                  "prediction_scorecard": grade_predictions(px, raw), "missing_data": [m["label"] for m in missing],
                  "market_risk": risk}
        print("2/6 Evidence: fetching known sources directly...")
        notes, dropped, srclog, need = gather_direct(session, THEMES, TODAY, ck=ck)
        if need:
            print(f"    themes {need} couldn't be read well enough; using Claude search for those only")
            n2, d2 = gather(session, ck, only=need)
            notes, dropped = notes + n2, dropped + d2
        packet["notes"], packet["sources"] = notes, srclog
        packet["sector_base_rates"] = sector_base_rates(packet["history_by_regime"])
        print(f"    {len(notes)} verified notes, {len(dropped)} dropped; "
              f"{sum(x['status'] == 'used' for x in srclog)}/{len(srclog)} sources used")
        ck.save("missing", missing)
        ck.save("dropped", dropped)
        ck.save("packet", json.loads(json.dumps(packet, default=str)))
        packet = ck.get("packet")
    fred, facts, calc, notes = packet["fred"], packet["facts"], packet["calc"], packet["notes"]
    packet_text = render_packet(packet)

    print("3/6 Four independent reasoning runs (Sonnet + Opus batched; Gemini + Mistral free)...")
    runs = reason(session, packet_text, ck)

    print("4/6 Audit, combine, critic...")
    auditor = Auditor(fred=fred, notes=notes, calcs=set(calc), sectors=set(SECTORS), facts=facts)
    audit_log = audit_runs(runs, auditor)
    final, moves = combine(runs, view, packet)
    packet["factor_view_combined"] = moves
    crit = critic(session, final, runs, packet_text, ck)
    for s in apply_critic_flags(final, crit):
        print(f"    critic flagged {s}: tilt moved one step toward neutral")
    serious = crit.get("overall") == "FAIL" or any(
        v.get("status") == "FAIL" and final.get(s, {}).get("tilt", 0) for s, v in (crit.get("sectors") or {}).items())
    status = "NEEDS_REVIEW" if serious else "OK"

    print("5/6 Saving...")
    if not ck.has("predictions_logged"):
        log_predictions(runs)
        ck.save("predictions_logged", True)
    new_view = {"date": TODAY.isoformat(), "status": status, "regime": calc["regime"], "fed": calc["fed_direction"],
                "tilts": {s: v["tilt"] for s, v in final.items()},
                "sector_probabilities": {s: v["p"] for s, v in final.items()}, "factor_view": moves,
                "weight_ranges_%": {s: v["range_%"] for s, v in final.items()}, "triggers": packet["triggers"],
                "why": packet.get("why_this_run", []),
                "key_risks": sorted({k for r in runs for k in r.get("key_risks") or [] if isinstance(k, str)}),
                "upcoming_events": merge_events(runs)}
    if status == "OK":
        write_json(state_path("macro_view.json"), new_view)
    elif not ck.has("review_requested"):
        # flagged views wait for your APPROVE / REJECT; the previous view stays in use meanwhile
        ck.save("review_requested", request_macro_review(new_view, crit).get("url"))
    packet["review_url"] = ck.get("review_requested")
    if not ck.has("macro_ledger"):
        mom = packet.get("momentum_rule") or {}
        ledger.record_macro(TODAY.isoformat(), {s: {"etf": SECTORS[s], "base_p": v["base_p"], "p": v["p"],
                                                    "disagreement_pts": v["disagreement_pts"], "tilt": v["tilt"],
                                                    "momentum_rank": (mom.get(s) or {}).get("rank"),
                                                    "momentum_p": (mom.get(s) or {}).get("p", 0.5)}
                                                for s, v in final.items()})
        hist = read_json(state_path("macro_etf_history.json"), [])
        hist.append({"date": TODAY.isoformat(), "macro": etf_weights({s: v["tilt"] for s, v in final.items()}),
                     "momentum": etf_weights({s: (mom.get(s) or {}).get("tilt", 0) for s in SECTORS})})
        write_json(state_path("macro_etf_history.json"), hist)
        ck.save("macro_ledger", True)
    if not ck.has("baseline_saved"):
        save_baseline(fred, facts)
        ck.save("baseline_saved", True)
    write_json(folder / "macro_view.json", new_view)
    write_json(folder / "full_run.json", {"packet": packet, "runs": runs, "final": final, "critic": crit, "audit": audit_log,
                                          "dropped_notes": dropped, "missing": missing})
    (folder / "packet_as_sent.md").write_text(packet_text)
    report_path = folder / "report.md"
    report_path.write_text(report(final, runs, crit, audit_log, packet, notes, dropped, missing, status, session.spent))

    print("6/6 Email...")
    if not ck.has("emailed"):
        email(final, status, crit, packet, report_path, session.spent)
        ck.save("emailed", True)
    ck.complete()
    for s, v in final.items():
        print(f"  {s:<24}{v['tilt']:+d}   {v['range_%'][0]}–{v['range_%'][1]}%")
    return {"status": status}


if __name__ == "__main__":
    run_stage("macro", main)
