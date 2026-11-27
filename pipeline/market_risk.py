"""
MARKET & RECESSION RISK  (plain statistics; runs inside the weekly macro check, no AI)

Two probabilities, each from a small logistic model fit on decades of free FRED + S&P 500 data, plus
the indicator readings behind them:

  Recession within 12 months   monthly since 1972 (7 recessions). Inputs: 10-yr minus 3-month Treasury
                               spread, Chicago Fed financial conditions (NFCI), Sahm rule (real time),
                               6-month change in jobless claims, S&P 500 6-month return.
                               Benchmarks shown alongside: the NY Fed-style yield-curve model and the
                               Chauvet-Piger "are we in one now" probability (FRED).
  S&P 500 pullback of 10%+     monthly since 1987 (Moody's Baa spread; FRED keeps only ~3 years of high-yield spreads). Inputs: 1-month
  within 3 months              realized volatility, S&P vs its 200-day average, Baa corporate spread
                               and its 3-month change, NFCI.

Geopolitics: the Geopolitical Risk Index (Caldara & Iacoviello) and economic policy uncertainty are tested
as extra pullback-model inputs and kept only if they improve its out-of-sample accuracy; they, trade policy
uncertainty, oil volatility and the oil futures curve are shown as readings either way.

Honesty checks: each model is also refit month by month using only data available at the time
(out of sample), and its accuracy (AUC: 0.5 = coin flip, 1 = perfect) is reported with the result.
These are information for the macro agent and you; they don't move money on their own.
Saved: state/market_risk.json (latest) and state/market_risk_history.csv (for grading later).
"""
import math

import numpy as np
import pandas as pd

from .util import now_et, state_path, write_json

TODAY = now_et().date()
RECESSION_HORIZON_M = 12
PULLBACK_DAYS, PULLBACK_DEPTH = 63, 0.10
RIDGE = 1.0
P_MIN, P_MAX = 0.02, 0.95
SERIES = {"GS10": "1953-01-01", "TB3MS": "1953-01-01", "T10Y3M": "1982-01-01", "NFCI": "1971-01-01",
          "SAHMREALTIME": "1959-01-01", "ICSA": "1967-01-01", "USREC": "1953-01-01",
          "BAMLH0A0HYM2": "1996-12-01", "RECPROUSM156N": "1967-01-01",
          "BAA10Y": "1986-01-01",
          "USEPUINDXD": "1985-01-01", "EPUTRADE": "1985-01-01", "OVXCLS": "2007-05-01"}
GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
# Candidate inputs for the pullback model: kept only if they improve its out-of-sample accuracy
OPTIONAL_PB = {"gpr": ("GPRD", "Geopolitical Risk Index, 30-day average (log)"),
               "epu": ("USEPUINDXD", "Economic policy uncertainty, 30-day average (log)")}
MIN_AUC_GAIN = 0.01
MONTH_CODES = "FGHJKMNQUVXZ"
REC_FEATURES = {"term_spread": "10-yr minus 3-month Treasury spread (pts)",
                "nfci": "Chicago Fed financial conditions (above 0 = tighter than average)",
                "sahm": "Sahm rule, real time (0.5+ has marked every recession start)",
                "claims_6m": "Jobless claims, 6-month change (%)",
                "spx_6m": "S&P 500, 6-month return (%)"}
PB_FEATURES = {"log_vol_1m": "S&P 500 1-month realized volatility (log)",
               "trend": "S&P 500 vs its 200-day average (%)",
               "credit_spread": "Baa corporate bond spread over 10-yr Treasury (pts)",
               "credit_change_3m": "Baa spread, 3-month change (pts)",
               "nfci": "Chicago Fed financial conditions"}


# ==================================================================== small logistic regression (ridge)
def fit_logit(X, y, lam=RIDGE, iters=50):
    X, y = np.asarray(X, float), np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    pen = np.full(len(w), lam)
    pen[0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + pen * w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(pen) + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return {"w": w, "mu": mu, "sd": sd}


def predict(m, X):
    Z = (np.atleast_2d(np.asarray(X, float)) - m["mu"]) / m["sd"]
    return 1 / (1 + np.exp(-np.clip(m["w"][0] + Z @ m["w"][1:], -30, 30)))


def drivers(m, x, names):
    """Each input's push on today's log-odds vs an average month (positive = raises the risk)."""
    z = (np.asarray(x, float) - m["mu"]) / m["sd"]
    out = [{"input": names[k], "value": round(float(x[i]), 3), "push": round(float(m["w"][i + 1] * z[i]), 2)}
           for i, k in enumerate(names)]
    return sorted(out, key=lambda d: -abs(d["push"]))


def auc(p, y):
    p, y = np.asarray(p, float), np.asarray(y, int)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().values
    return round(float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))), 3)


def out_of_sample(X, y, dates, horizon, start):
    """Refit each month on samples whose outcome was already known then; predict that month."""
    ps, ys = [], []
    for i, d in enumerate(dates):
        if d < start:
            continue
        known = [j for j in range(i) if j + horizon <= i]
        if len(known) < 60 or len(set(y[known])) < 2:
            continue
        ps.append(float(predict(fit_logit(X[known], y[known]), X[i])[0]))
        ys.append(int(y[i]))
    if not ps:
        return {}
    base = float(np.mean(ys))
    brier = float(np.mean((np.array(ps) - np.array(ys)) ** 2))
    brier0 = float(np.mean((base - np.array(ys)) ** 2))
    return {"auc": auc(ps, ys), "months": len(ps), "from": str(start)[:7],
            "brier_skill_%": round(100 * (1 - brier / brier0), 1) if brier0 else None}


# ==================================================================== data
def monthly(s, how="mean"):
    s = s.dropna()
    return (s.resample("ME").mean() if how == "mean" else s.resample("ME").last()).dropna()


def gpr_daily(get=None):
    """Caldara & Iacoviello daily Geopolitical Risk Index (counts of war/terror/tension articles)."""
    import io
    import requests
    r = (get or requests.get)(GPR_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 (personal research)"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    df = pd.read_excel(io.BytesIO(r.content))
    cols = {str(c).lower(): c for c in df.columns}
    val = cols.get("gprd") or next(c for k, c in cols.items() if k.startswith("gpr"))
    when = cols.get("date") or cols.get("day") or df.columns[0]
    idx = pd.to_datetime(df[when].astype(str), errors="coerce", format="mixed")
    return pd.Series(pd.to_numeric(df[val], errors="coerce").values, index=idx).dropna().sort_index()


def oil_curve():
    """(front-month WTI, ~6-month-out WTI) closes; front above later = backwardation (tight supply now)."""
    import yfinance as yf
    t = TODAY
    k = t.month - 1 + 7
    sym = f"CL{MONTH_CODES[k % 12]}{(t.year + k // 12) % 100:02d}.NYM"
    px = yf.download(["CL=F", sym], period="10d", progress=False, auto_adjust=True)["Close"].dropna(how="all")
    return float(px["CL=F"].dropna().iloc[-1]), float(px[sym].dropna().iloc[-1]), sym


def load(fred_get, spx=None, extra=None):
    raw = {}
    for sid, start in SERIES.items():
        try:
            raw[sid] = fred_get(sid, start)
        except Exception as e:
            print(f"    ! market risk: FRED {sid} unavailable ({str(e)[:60]})")
    if spx is None:
        import yfinance as yf
        spx = yf.download("^GSPC", start="1970-01-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(spx, pd.DataFrame):
            spx = spx.iloc[:, 0]
    if extra is not None:                       # tests pass these in
        raw.update(extra)
    else:
        try:
            raw["GPRD"] = gpr_daily()
        except Exception as e:
            print(f"    ! Geopolitical Risk Index unavailable ({str(e)[:60]})")
        try:
            raw["OIL_CURVE"] = oil_curve()
        except Exception as e:
            print(f"    ! oil futures curve unavailable ({str(e)[:60]})")
    return raw, spx.dropna()


def recession_frame(raw, spx):
    spread = monthly(raw["GS10"]) - monthly(raw["TB3MS"])
    if "T10Y3M" in raw:                                    # daily spread: fills the latest month early
        spread = spread.combine_first(monthly(raw["T10Y3M"]))
        spread.loc[monthly(raw["T10Y3M"]).index[-1]] = monthly(raw["T10Y3M"]).iloc[-1]
    claims = monthly(raw["ICSA"])
    px = monthly(spx, "last")
    f = pd.DataFrame({"term_spread": spread, "nfci": monthly(raw["NFCI"]),
                      "sahm": monthly(raw["SAHMREALTIME"]).shift(1),        # published the month after
                      "claims_6m": 100 * (claims / claims.shift(6) - 1),
                      "spx_6m": 100 * (px / px.shift(6) - 1)})
    rec = monthly(raw["USREC"], "last")
    fut = pd.concat([rec.shift(-k) for k in range(1, RECESSION_HORIZON_M + 1)], axis=1)
    f["y"] = fut.max(axis=1).where(fut.notna().all(axis=1))
    f["sahm"] = f["sahm"].ffill(limit=2)
    return f


def pullback_frame(raw, spx):
    r = spx.pct_change()
    vol = r.rolling(21).std() * math.sqrt(252)
    trend = 100 * (spx / spx.rolling(200).mean() - 1)
    align = lambda s, limit: s.reindex(s.index.union(spx.index)).ffill(limit=limit).reindex(spx.index)
    # FRED keeps only ~3 years of the ICE high-yield spread, too short to learn from: the model uses Moody's
    # Baa spread (daily since 1986); the high-yield spread is still shown as a reading
    hy = align(raw["BAA10Y"].dropna(), 5)
    nfci = align(raw["NFCI"].dropna(), 10)            # weekly: carried to the following days
    fwd_min = spx[::-1].rolling(PULLBACK_DAYS, min_periods=PULLBACK_DAYS).min()[::-1].shift(-1)
    d = pd.DataFrame({"log_vol_1m": np.log(vol), "trend": trend, "credit_spread": hy,
                      "credit_change_3m": hy - hy.shift(63), "nfci": nfci,
                      "y": (fwd_min / spx - 1 <= -PULLBACK_DEPTH).astype(float).where(fwd_min.notna())})
    for name, (sid, _) in OPTIONAL_PB.items():
        if sid in raw and len(raw[sid].dropna()):
            d[name] = np.log(align(raw[sid].dropna().rolling(30, min_periods=10).mean(), 10).clip(lower=1e-6))
    ends = d.index.to_series().groupby(d.index.to_period("M")).max()
    m = d.loc[ends.values]
    if d.index[-1] not in m.index:                          # today, even mid-month
        m = pd.concat([m, d.iloc[[-1]]])
    return m


def fit_and_score(frame, names, horizon, oos_start):
    cols = list(names)
    have = frame.dropna(subset=cols)
    train = have.dropna(subset=["y"])
    X, y = train[cols].values, train["y"].values.astype(int)
    m = fit_logit(X, y)
    now = have.iloc[-1]
    p = min(P_MAX, max(P_MIN, float(predict(m, now[cols].values)[0])))   # a handful of past events can't justify certainty
    return {"probability": round(p, 3), "base_rate": round(float(y.mean()), 3), "as_of": now.name.date().isoformat(),
            "drivers": drivers(m, now[cols].values, names), "samples": len(train),
            "trained_from": train.index[0].date().isoformat(),
            "out_of_sample": out_of_sample(X, y, list(train.index), horizon, pd.Timestamp(oos_start)),
            "history": [(d.date().isoformat(), round(float(v), 3)) for d, v in
                        zip(have.index[-36:], predict(m, have[cols].values[-36:]))]}


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def indicators(raw, spx, rf, pf):
    """The readings, each with a plain rule of thumb."""
    last = lambda s: (float(s.dropna().iloc[-1]), s.dropna().index[-1].date().isoformat())
    out = []
    sp, sd = last(rf["term_spread"])
    if "T10Y3M" in raw and len(raw["T10Y3M"].dropna()):
        sd = raw["T10Y3M"].dropna().index[-1].date().isoformat()        # the daily data's date, not the month end
    inv = int((rf["term_spread"].dropna().tail(24) < 0).sum())
    out.append({"name": "Yield curve (10y - 3m)", "value": round(sp, 2), "as_of": sd,
                "reading": f"inverted ({inv} of the last 24 months)" if sp < 0 else
                f"positive; inverted {inv} of the last 24 months" + (" (un-inverting often precedes recessions)" if inv >= 6 else "")})
    s, d = last(raw["SAHMREALTIME"])
    out.append({"name": "Sahm rule (real time)", "value": round(s, 2), "as_of": d,
                "reading": "TRIGGERED (0.5+)" if s >= 0.5 else "rising" if s >= 0.3 else "calm"})
    hy = raw["BAMLH0A0HYM2"].dropna() if "BAMLH0A0HYM2" in raw else raw["BAA10Y"].dropna()
    h, d = last(hy)
    chg = h - float(hy.iloc[-64]) if len(hy) > 64 else float("nan")
    pct = float((hy < h).mean() * 100)
    out.append({"name": "High-yield credit spread", "value": round(h, 2), "as_of": d, "change_3m": round(chg, 2),
                "reading": f"{pct:.0f}th percentile since {hy.index[0].year}; " + ("widening fast" if chg >= 1 else
                                                                     "widening" if chg >= 0.3 else "stable/tightening")})
    n, d = last(raw["NFCI"])
    out.append({"name": "Chicago Fed financial conditions (NFCI)", "value": round(n, 2), "as_of": d,
                "reading": "tighter than average" if n > 0 else "looser than average"})
    t = float(pf["trend"].dropna().iloc[-1])
    out.append({"name": "S&P 500 vs 200-day average", "value": f"{t:+.1f}%", "as_of": spx.index[-1].date().isoformat(),
                "reading": "below (downtrend)" if t < 0 else "above (uptrend)"})
    v = math.exp(float(pf["log_vol_1m"].dropna().iloc[-1]))
    vp = float((np.exp(pf["log_vol_1m"].dropna()) < v).mean() * 100)
    out.append({"name": "S&P 500 1-month volatility", "value": f"{v * 100:.0f}%", "as_of": spx.index[-1].date().isoformat(),
                "reading": f"{vp:.0f}th percentile since {pf['log_vol_1m'].dropna().index[0].year}" + (" (stressed)" if vp >= 80 else "")})
    for sid, name, since in (("GPRD", "Geopolitical Risk Index (30-day avg)", "1985"),
                             ("USEPUINDXD", "Economic policy uncertainty (30-day avg)", "1985"),
                             ("EPUTRADE", "Trade policy uncertainty (monthly)", "1985"),
                             ("OVXCLS", "Oil volatility (OVX)", "2007")):
        if sid in raw and len(raw[sid].dropna()) > 60:
            x = raw[sid].dropna()
            x = x.rolling(30, min_periods=10).mean().dropna() if sid in ("GPRD", "USEPUINDXD") else x
            v, d = float(x.iloc[-1]), x.index[-1].date().isoformat()
            pct = float((x < v).mean() * 100)
            out.append({"name": name, "value": round(v, 1), "as_of": d,
                        "reading": f"{pct:.0f}th percentile since {since}" + (" (elevated)" if pct >= 80 else "")})
    if raw.get("OIL_CURVE"):
        front, later, sym = raw["OIL_CURVE"]
        slope = 100 * (front / later - 1)
        out.append({"name": "Oil futures curve (front vs ~6 months out)", "value": f"{slope:+.1f}%", "as_of": TODAY.isoformat(),
                    "reading": ("steep backwardation: oil is scarce NOW (real supply squeeze)" if slope >= 5 else
                                "backwardation: near-term supply tight" if slope > 0.5 else
                                "contango: supply ample; price moves are more fear than shortage")})
    c, d = last(rf["claims_6m"])
    d = raw["ICSA"].dropna().index[-1].date().isoformat()
    out.append({"name": "Jobless claims, 6-month change", "value": f"{c:+.0f}%", "as_of": d,
                "reading": "rising sharply" if c >= 20 else "rising" if c >= 8 else "stable"})
    return out


def compute(fred_get, spx=None, extra=None):
    raw, spx = load(fred_get, spx, extra)
    need = {"GS10", "TB3MS", "NFCI", "SAHMREALTIME", "ICSA", "USREC", "BAA10Y"}
    if need - set(raw):
        return {"date": TODAY.isoformat(), "error": "missing FRED series: " + ", ".join(sorted(need - set(raw)))}
    rf, pf = recession_frame(raw, spx), pullback_frame(raw, spx)
    rec = fit_and_score(rf, REC_FEATURES, RECESSION_HORIZON_M, "1990-01-01")
    pb_names, tested = dict(PB_FEATURES), {}
    for name, (sid, label) in OPTIONAL_PB.items():
        if name not in pf:
            tested[label] = {"kept": False, "why": "data unavailable"}
            continue
        common = pf.dropna(subset=list(PB_FEATURES) + [name])
        a0 = fit_and_score(common, PB_FEATURES, 3, "2000-01-01")["out_of_sample"].get("auc")
        a1 = fit_and_score(common, {**PB_FEATURES, name: label}, 3, "2000-01-01")["out_of_sample"].get("auc")
        keep = a0 is not None and a1 is not None and a1 - a0 >= MIN_AUC_GAIN
        tested[label] = {"kept": keep, "auc_without": a0, "auc_with": a1}
        if keep:
            pb_names[name] = label
    pb = fit_and_score(pf, pb_names, 3, "2000-01-01")
    pb["inputs_tested"] = tested
    spread = float(rf["term_spread"].dropna().iloc[-1])
    rec["benchmarks"] = {"ny_fed_style_yield_curve_model": round(_norm_cdf(-0.5333 - 0.6330 * spread), 3)}
    if "RECPROUSM156N" in raw and len(raw["RECPROUSM156N"].dropna()):
        s = raw["RECPROUSM156N"].dropna()
        rec["benchmarks"]["chauvet_piger_in_recession_now"] = round(float(s.iloc[-1]) / 100, 3)
        rec["benchmarks"]["chauvet_piger_as_of"] = s.index[-1].date().isoformat()
    out = {"date": TODAY.isoformat(), "spx_as_of": spx.index[-1].date().isoformat(), "recession_12m": rec, "pullback_10pct_3m": pb,
           "indicators": indicators(raw, spx, rf, pf)}
    out["summary"] = summary(out)
    return out


def level(p, base):
    r = p / base if base else 1
    return "HIGH" if r >= 2 or p >= 0.5 else "elevated" if r >= 1.3 else "low" if r <= 0.7 else "normal"


def summary(r):
    rec, pb = r["recession_12m"], r["pullback_10pct_3m"]
    return (f"Recession within 12 months: {rec['probability']:.0%} ({level(rec['probability'], rec['base_rate'])}; "
            f"typical {rec['base_rate']:.0%}). S&P 500 10%+ pullback within 3 months: {pb['probability']:.0%} "
            f"({level(pb['probability'], pb['base_rate'])}; typical {pb['base_rate']:.0%}).")


def calc_entries(r):
    """Compact entries for the macro packet's CALCULATIONS table (cite CALC:recession_risk etc.)."""
    if not r or r.get("error"):
        return {}
    rec, pb = r["recession_12m"], r["pullback_10pct_3m"]
    top = lambda x: ", ".join(f"{d['input']} {d['push']:+.1f}" for d in x["drivers"][:3])
    return {"recession_risk": {"p_12m": rec["probability"], "typical": rec["base_rate"],
                               "level": level(rec["probability"], rec["base_rate"]),
                               "yield_curve_model": rec["benchmarks"].get("ny_fed_style_yield_curve_model"),
                               "in_recession_now_p": rec["benchmarks"].get("chauvet_piger_in_recession_now"),
                               "top_drivers": top(rec), "oos_auc": rec["out_of_sample"].get("auc")},
            "pullback_risk": {"p_10pct_3m": pb["probability"], "typical": pb["base_rate"],
                              "level": level(pb["probability"], pb["base_rate"]),
                              "top_drivers": top(pb), "oos_auc": pb["out_of_sample"].get("auc")},
            "risk_indicators": {i["name"]: f"{i['value']} ({i['reading']})" for i in r["indicators"]}}


def report_md(r):
    if not r or r.get("error"):
        return ["## Market & recession risk", f"Unavailable: {(r or {}).get('error', 'not computed')}", ""]
    L = ["## Market & recession risk", r["summary"], ""]
    for key, title in (("recession_12m", "Recession within 12 months"), ("pullback_10pct_3m", "S&P 500 pullback of 10%+ within 3 months")):
        x = r[key]
        o = x["out_of_sample"]
        L += [f"**{title}: {x['probability']:.0%}** (typical {x['base_rate']:.0%}; model trained on {x['samples']} months "
              f"since {x['trained_from'][:4]}; out-of-sample accuracy AUC {o.get('auc')} since {o.get('from')}, "
              f"Brier skill {o.get('brier_skill_%')}%)",
              "", "| Input | Now | Push on risk |", "|---|---|---|"]
        L += [f"| {d['input']} | {d['value']} | {d['push']:+.2f} |" for d in x["drivers"]]
        for lab, t in (x.get("inputs_tested") or {}).items():
            L.append(f"- Tested input *{lab}*: " + ("KEPT" if t["kept"] else "not kept") +
                     (f" (accuracy {t['auc_without']} → {t['auc_with']})" if t.get("auc_with") is not None else f" ({t.get('why')})"))
        if x.get("benchmarks"):
            b = x["benchmarks"]
            L += ["", f"Benchmarks: NY Fed-style yield-curve model {b.get('ny_fed_style_yield_curve_model', 0):.0%}; "
                      f"Chauvet-Piger probability we're in a recession now "
                      f"{b.get('chauvet_piger_in_recession_now', float('nan')):.0%} (as of {b.get('chauvet_piger_as_of')})"]
        L.append("")
    L += ["| Indicator | Now | As of | Reading |", "|---|---|---|---|"]
    L += [f"| {i['name']} | {i['value']} | {i['as_of']} | {i['reading']} |" for i in r["indicators"]]
    return L + ["", "*Statistical models on public data: they flag risky periods, with false alarms; they don't time tops.*", ""]


def save(r):
    if not r or r.get("error"):
        return
    write_json(state_path("market_risk.json"), r)
    p = state_path("market_risk_history.csv")
    row = pd.DataFrame([{"date": r["date"], "recession_12m": r["recession_12m"]["probability"],
                         "pullback_3m": r["pullback_10pct_3m"]["probability"],
                         "spx_as_of": r.get("spx_as_of")}])
    old = pd.read_csv(p) if p.exists() else pd.DataFrame()
    pd.concat([old[old.get("date", pd.Series(dtype=str)) != r["date"]] if len(old) else old, row]).to_csv(p, index=False)


def tripwire(r, prev):
    """A reason to run the full macro agent early: a probability crossed into HIGH since last week."""
    if not r or r.get("error") or not prev or prev.get("error"):
        return None
    out = []
    for key, name in (("recession_12m", "recession risk"), ("pullback_10pct_3m", "pullback risk")):
        now, before = r[key], prev.get(key) or {}
        if level(now["probability"], now["base_rate"]) == "HIGH" and \
                level(before.get("probability", 0), before.get("base_rate", 1)) != "HIGH":
            out.append(f"{name} rose to HIGH ({now['probability']:.0%})")
    return "; ".join(out) or None
