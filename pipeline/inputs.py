"""
BETTER INPUTS for the judges (improvement #5), all from free data, each as one compact dossier table:

  sensitivity   how the stock has moved with rates, oil, the dollar, credit and inflation
                expectations (weekly, 3 years, net of the market). Also used by code for the
                "shared driver" limit, so hidden common bets are measured, not guessed.
  valuation     what's priced in: price-to-sales and operating-earnings yield as percentiles vs
                its sub-industry and vs its own 5 years; the options market's expected earnings
                move (when earnings fall in the window); short interest.
  peers         the stock next to its 4-5 closest sub-industry peers (growth, margin, valuation,
                3-month return).
  track_record  last 8 earnings reactions vs its sector, revenue growth steadiness, and whether
                management has tended to raise or cut guidance (built up from the releases the
                team already reads).
"""
import math

import numpy as np
import pandas as pd

from . import config

FACTOR_TICKERS = ["^TNX", "CL=F", "UUP", "HYG", "IEF", "TIP", "SPY"]
FACTOR_NAMES = {"rates_10y": "10-yr yield", "oil": "oil", "dollar": "dollar", "credit": "credit (HY vs Treasuries)",
                "inflation_exp": "inflation expectations"}


# ==================================================================== market data (network)
def fetch_prices(tickers, years=3):
    import yfinance as yf
    syms = sorted(set(tickers) | set(FACTOR_TICKERS))
    d = yf.download([t.replace(".", "-") if not t.startswith("^") else t for t in syms], period=f"{years}y",
                    progress=False, auto_adjust=True, threads=True)["Close"]
    d.columns = [c.replace("-", ".") if not c.startswith("^") else c for c in d.columns]
    return d.sort_index()


def options_move(ticker, earnings_date, price):
    """Expected earnings move priced by the options market: at-the-money straddle / price for the
    first expiry after the earnings date. None when Yahoo has no usable quotes."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker.replace(".", "-"))
        exp = [e for e in tk.options if e >= earnings_date]
        if not exp or not price:
            return None
        ch = tk.option_chain(exp[0])
        k = min(ch.calls.strike, key=lambda x: abs(x - price))
        c = ch.calls[ch.calls.strike == k].iloc[0]
        p = ch.puts[ch.puts.strike == k].iloc[0]
        mid = ((c.bid + c.ask) / 2 if c.ask > 0 else c.lastPrice) + ((p.bid + p.ask) / 2 if p.ask > 0 else p.lastPrice)
        move = float(mid / price)
        return round(move * 100, 1) if 0 < move < 1 else None
    except Exception:
        return None


def estimates(ticker):
    """EPS estimate trend and revision counts (Yahoo). None when unavailable."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker.replace(".", "-"))
        trend, rev = tk.eps_trend, tk.eps_revisions
        out = {}
        if trend is not None and len(trend):
            trend.columns = [str(c).lower() for c in trend.columns]
            for per in ("0y", "+1y"):
                if per in trend.index:
                    row = trend.loc[per]
                    out[per] = {k: (float(row[c]) if c in row and row[c] == row[c] else None)
                                for k, c in (("now", "current"), ("30d_ago", "30daysago"), ("90d_ago", "90daysago"))}
        if rev is not None and len(rev):
            rev.columns = [str(c).lower() for c in rev.columns]
            if "0y" in rev.index:
                r = rev.loc["0y"]
                out["revisions_30d"] = {"up": int(r.get("uplast30days", 0) or 0), "down": int(r.get("downlast30days", 0) or 0)}
        return out or None
    except Exception:
        return None


def estimates_text(e):
    if not e:
        return "Analyst estimates: not available."
    parts = []
    for per, label in (("0y", "this fiscal year"), ("+1y", "next fiscal year")):
        x = e.get(per) or {}
        if x.get("now"):
            ch = lambda old: f"{(x['now'] / old - 1) * 100:+.1f}%" if old else "n/a"
            parts.append(f"EPS estimate {label} {x['now']:.2f} ({ch(x.get('30d_ago'))} vs 30 days ago, "
                         f"{ch(x.get('90d_ago'))} vs 90 days ago)")
    if e.get("revisions_30d"):
        parts.append(f"revisions last 30 days: {e['revisions_30d']['up']} up / {e['revisions_30d']['down']} down")
    return "Analyst estimates: " + ("; ".join(parts) if parts else "not available") + "."


def short_interest(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker.replace(".", "-")).info or {}
        v = info.get("shortPercentOfFloat")
        return round(float(v) * 100, 1) if v is not None else None
    except Exception:
        return None


# ==================================================================== sensitivities
def factor_changes(px):
    """Weekly factor moves: yield change in basis points; everything else in % (ratios for credit and
    inflation expectations: HYG/IEF up = spreads tightening; TIP/IEF up = expectations rising)."""
    w = px.resample("W-FRI").last()
    f = pd.DataFrame(index=w.index)
    if "^TNX" in w:
        tnx = w["^TNX"]
        f["rates_10y"] = tnx.diff() * (10 if tnx.median() > 20 else 100)   # older Yahoo quotes were yield x 10
    if "CL=F" in w:
        f["oil"] = w["CL=F"].pct_change(fill_method=None) * 100
    if "UUP" in w:
        f["dollar"] = w["UUP"].pct_change(fill_method=None) * 100
    if "HYG" in w and "IEF" in w:
        f["credit"] = (w["HYG"] / w["IEF"]).pct_change(fill_method=None) * 100
    if "TIP" in w and "IEF" in w:
        f["inflation_exp"] = (w["TIP"] / w["IEF"]).pct_change(fill_method=None) * 100
    return f.replace([np.inf, -np.inf], np.nan)


def sensitivities(px, tickers, benchmark="SPY", min_weeks=78):
    """{ticker: {factor: {"beta_%": excess return per one-std weekly factor move, "t": t-stat,
    "label": strong/mild/none, "sign": +/-}, "_dominant": factor or None}}."""
    if px is None or px.empty or not isinstance(px.index, pd.DatetimeIndex):
        return {}
    f = factor_changes(px)
    w = px.resample("W-FRI").last().pct_change(fill_method=None) * 100
    out = {}
    if benchmark not in w or f.empty:
        return out
    for t in tickers:
        if t not in w:
            continue
        y = (w[t] - w[benchmark]).rename("y")
        d = pd.concat([y, f], axis=1).dropna()
        if len(d) < min_weeks:
            continue
        X = d[f.columns]
        Xs = (X - X.mean()) / X.std().replace(0, np.nan)
        Xs = Xs.dropna(axis=1)
        A = np.column_stack([np.ones(len(Xs)), Xs.values])
        coef, *_ = np.linalg.lstsq(A, d.y.values, rcond=None)
        resid = d.y.values - A @ coef
        dof = max(1, len(d) - A.shape[1])
        s2 = float(resid @ resid / dof)
        try:
            se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
        except np.linalg.LinAlgError:
            continue
        row = {}
        for k, name in enumerate(Xs.columns, start=1):
            tval = coef[k] / se[k] if se[k] > 0 else 0.0
            row[name] = {"beta_%": round(float(coef[k]), 3), "t": round(float(tval), 1),
                         "label": "strong" if abs(tval) >= 3 else "mild" if abs(tval) >= 2 else "none",
                         "sign": "+" if coef[k] > 0 else "-"}
        sig = {k: v for k, v in row.items() if abs(v["t"]) >= 2}
        row["_dominant"] = max(sig, key=lambda k: abs(sig[k]["t"])) if sig else None
        row["_weekly_resid_sd_%"] = round(math.sqrt(s2), 3)
        out[t] = row
    return out


def sensitivity_text(s):
    if not s:
        return "Macro sensitivities: not enough price history."
    parts = []
    for k, name in FACTOR_NAMES.items():
        v = s.get(k)
        if not v:
            continue
        parts.append(f"{name} {'none' if v['label'] == 'none' else v['label'] + (' positive' if v['sign'] == '+' else ' negative')}"
                     + (f" (t {v['t']:+.1f})" if v["label"] != "none" else ""))
    dom = s.get("_dominant")
    return ("Macro sensitivities vs the market (3 yrs, weekly): " + "; ".join(parts)
            + (f". Dominant: {FACTOR_NAMES.get(dom, dom)}." if dom else ". No dominant macro factor."))


# ==================================================================== valuation, peers, track record
def _pct_rank(values, x):
    v = [a for a in values if a is not None and a == a]
    if x is None or x != x or len(v) < 5:
        return None
    return round(float(np.mean([a <= x for a in v]) * 100))


def valuation_rows(bench, feats):
    """Per ticker: P/S and operating-earnings yield plus their percentiles within the sub-industry
    (falls back to the sector when the sub-industry has fewer than 5 names)."""
    b = bench.set_index("ticker")
    ps = {t: (feats.get(t) or {}).get("ps_now") for t in b.index}
    ey = {t: b.loc[t].get("v_ebit_yield") for t in b.index}
    group = "sub_industry" if "sub_industry" in b else "sector"
    out = {}
    for t in b.index:
        g = b[b[group] == b.loc[t, group]].index if group in b else b.index
        if len(g) < 5:
            g = b[b.sector == b.loc[t, "sector"]].index
        out[t] = {"ps": ps.get(t), "ps_pct_peers": _pct_rank([ps.get(x) for x in g], ps.get(t)),
                  "ebit_yield_%": round(ey[t] * 100, 1) if ey.get(t) == ey.get(t) and ey.get(t) is not None else None,
                  "ebit_yield_pct_peers": _pct_rank([ey.get(x) for x in g], ey.get(t)),
                  "ps_pct_own_5y": (feats.get(t) or {}).get("ps_pct_5y")}
    return out


def peers(bench, t, n=5):
    b = bench.set_index("ticker")
    if t not in b.index:
        return []
    group = "sub_industry" if "sub_industry" in b and pd.notna(b.loc[t].get("sub_industry")) else "sector"
    cand = b[(b[group] == b.loc[t, group]) & (b.index != t)]
    if len(cand) < 3:
        cand = b[(b.sector == b.loc[t, "sector"]) & (b.index != t)]
    m = b.loc[t].get("mcap")
    if m and m == m and "mcap" in cand:
        cand = cand.assign(d=(np.log(cand.mcap.astype(float).clip(lower=1)) - math.log(max(float(m), 1))).abs()).sort_values("d")
    return list(cand.head(n).index)


def peer_table_text(bench, t, feats, vals):
    b = bench.set_index("ticker")
    rows = [t] + peers(bench, t)
    fmt = lambda x, s="": "n/a" if x is None or x != x else f"{x}{s}"
    lines = ["Peer table (ticker | revenue growth last yr % | op margin % | P/S | op-earnings yield % | 3-mo return %):"]
    for x in rows:
        if x not in b.index:
            continue
        g = ((feats.get(x) or {}).get("rev_growth_%") or [None])[-1]
        om = b.loc[x].get("q_op_margin")
        m3 = b.loc[x].get("mom_3m")
        v = vals.get(x) or {}
        lines.append(f"{x}{' (this stock)' if x == t else ''} | {fmt(g)} | {fmt(round(om * 100, 1) if om == om and om is not None else None)} | "
                     f"{fmt(v.get('ps'))} | {fmt(v.get('ebit_yield_%'))} | {fmt(round(m3 * 100, 1) if m3 == m3 and m3 is not None else None)}")
    return "\n".join(lines)


def valuation_text(v, opt_move=None, short=None, reactions=None, earnings_date=None):
    fmt = lambda x: "n/a" if x is None else f"{x}"
    parts = [f"P/S {fmt(v.get('ps'))} (percentile vs peers {fmt(v.get('ps_pct_peers'))}, vs own 5 yrs {fmt(v.get('ps_pct_own_5y'))})",
             f"operating-earnings yield {fmt(v.get('ebit_yield_%'))}% (percentile vs peers {fmt(v.get('ebit_yield_pct_peers'))}; higher = cheaper)"]
    if earnings_date:
        past = [abs(r["vs_sector_%"]) for r in (reactions or [])]
        parts.append(f"earnings {earnings_date}: options price a ±{fmt(opt_move)}% move"
                     + (f" vs an average ±{np.mean(past):.1f}% over the last {len(past)} reports" if past else ""))
    parts.append(f"short interest {fmt(short)}% of float")
    return "What's priced in: " + "; ".join(parts) + ". (Own-history P/S uses today's share count.)"


def track_record_text(f, guidance):
    r = (f or {}).get("reactions") or []
    g = (f or {}).get("rev_growth_%") or []
    parts = []
    if r:
        beats = sum(x["vs_sector_%"] > 0 for x in r)
        parts.append(f"last {len(r)} earnings reactions vs sector: " + ", ".join(f"{x['vs_sector_%']:+.1f}%" for x in r)
                     + f" ({beats}/{len(r)} positive)")
    if len(g) >= 2:
        sd = float(np.std(g))
        parts.append(f"annual revenue growth {', '.join(f'{x:+.0f}%' for x in g)} ({'steady' if sd < 5 else 'variable'})")
    if guidance:
        c = {k: sum(1 for x in guidance if x.get("guidance") == k) for k in ("raised", "maintained", "lowered")}
        parts.append(f"guidance in the last {len(guidance)} releases: raised {c['raised']}, maintained {c['maintained']}, "
                     f"lowered {c['lowered']}")
    return "Earnings track record: " + ("; ".join(parts) if parts else "not enough history") + "."


def normalize_guidance(g):
    g = str(g or "").lower()
    if any(w in g for w in ("raise", "increas", "above", "higher")):
        return "raised"
    if any(w in g for w in ("lower", "cut", "reduc", "below", "decreas")):
        return "lowered"
    if any(w in g for w in ("maintain", "reaffirm", "unchanged", "in line", "reiterat")):
        return "maintained"
    return None


def gather(tickers, bench, feats, guidance_hist, market=None, per_ticker=None):
    """Dossier inputs for each ticker: {ticker: {"sensitivity": {...}, "items": [(kind, text), ...]}}.
    market: price table (tests pass a fake); per_ticker: (options_move, short_interest) functions."""
    if market is not None:
        px = market
    else:
        try:
            px = fetch_prices(tickers)
        except Exception as e:                     # sensitivities are optional: never stop the team for them
            print(f"    ! price history for sensitivities unavailable ({str(e)[:80]})")
            px = pd.DataFrame()
    per_ticker = tuple(per_ticker or (options_move, short_interest, estimates))
    opt_fn, short_fn = per_ticker[:2]
    est_fn = per_ticker[2] if len(per_ticker) > 2 else (lambda t: None)
    sens = sensitivities(px, tickers)
    vals = valuation_rows(bench, feats)
    b = bench.set_index("ticker")
    horizon = (pd.Timestamp.today() + pd.Timedelta(days=30)).date().isoformat()
    out = {}
    for t in tickers:
        if t not in b.index:
            continue
        ed = b.loc[t].get("earnings_date")
        ed = ed if isinstance(ed, str) and ed <= horizon else None
        price = b.loc[t].get("price")
        f = feats.get(t) or {}
        items = [("sensitivity", sensitivity_text(sens.get(t))),
                 ("valuation", valuation_text(vals.get(t) or {}, opt_fn(t, ed, price) if ed else None, short_fn(t),
                                              f.get("reactions"), ed)),
                 ("estimates", estimates_text(est_fn(t))),
                 ("peers", peer_table_text(bench, t, feats, vals)),
                 ("track_record", track_record_text(f, (guidance_hist or {}).get(t)))]
        out[t] = {"sensitivity": sens.get(t), "items": items}
    return out


def dominant_factor(s):
    return (s or {}).get("_dominant")


def limit_dossier(items, max_items=None, max_chars=None):
    """Keep the dossier readable: drop the least important items first (extra headlines, then extra
    metrics, then extra filing quotes), then shorten the longest texts. Ids are renumbered after."""
    max_items = max_items or config.DOSSIER_MAX_ITEMS
    max_chars = max_chars or config.DOSSIER_MAX_CHARS
    items = list(items)
    for kind, keep in (("headline", 3), ("metric", 6), ("filing_quote", 3), ("catalyst", 5), ("fundamentals", 5)):
        size = lambda: sum(len(i["text"]) for i in items)
        if len(items) <= max_items and size() <= max_chars:
            break
        seen = 0
        kept = []
        for i in items:
            if i["kind"] == kind:
                seen += 1
                if seen > keep:
                    continue
            kept.append(i)
        items = kept
    while sum(len(i["text"]) for i in items) > max_chars:
        longest = max(items, key=lambda i: len(i["text"]))
        if len(longest["text"]) < 300:
            break
        longest["text"] = longest["text"][: int(len(longest["text"]) * 0.8)] + " …"
    for n, i in enumerate(items, 1):
        i["id"] = f"D{n}"
    return items
