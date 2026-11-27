"""
TECHNICAL-INDICATOR BACKTEST  —  runs with the screen backtest (python -m pipeline.screentest). Analysis only.

Do chart-style indicators (moving averages, breakouts, support and resistance, RSI, Bollinger bands, MACD...) say
anything about a stock's next 4 weeks against its sector, alone or combined, and would adding them improve the
screen? Same samples and rules as pipeline/screentest.py: month-ends since 2010, each indicator computed only from
prices up to that day, ranked inside the sector.

Every indicator is scored in the direction chartists read as bullish, fixed before looking at results, so a
NEGATIVE result means the usual reading was backwards in this data, not that we get to flip it.

  alone      each indicator's monthly rank correlation with the next 4 weeks (IC), in both halves of the history,
             and what a top-2-per-sector portfolio built on it alone earned against the equal-weighted universe
  patterns   yes/no events (new 3-month high, bounce off support, golden cross, RSI under 30...): what the stocks
             showing one did next
  together   on the out-of-sample months: all indicators in equal parts; walk-forward weights by past IC; a
             walk-forward ridge; and the current screen with the ridge mix blended in at 20%, each against the
             current screen alone

Only closing prices are cached, so indicators that need volume or daily highs and lows (on-balance volume, ATR, the
true stochastic) are not here. Outputs: reports/screentest/technical.md, technical.png, state/tatest.json.
"""
import numpy as np
import pandas as pd

from . import screentest as st
from .util import now_et

BLEND = 0.20            # share given to the technical mix in "current screen + technical"

# name: (what a HIGH score means, the bullish reading)
INDICATORS = {
    "above_200dma": "Price far above its 200-day average (uptrend)",
    "above_50dma": "Price far above its 50-day average",
    "golden_cross": "50-day average above the 200-day (golden-cross state)",
    "ma50_slope": "50-day average rising",
    "breakout_3m": "At or through its 3-month high (resistance breakout)",
    "above_52w_low": "Far above its 52-week low",
    "near_support": "Close to its 3-month low (buy at support)",
    "rsi_oversold": "Low 14-day RSI (oversold)",
    "bollinger_low": "Near or under the lower Bollinger band",
    "stochastic_low": "Low in its 14-day range (stochastic oversold)",
    "macd_hist": "MACD above its signal line",
    "roc_1m": "Up over the last month",
    "roc_3m": "Up over the last 3 months",
    "roc_6m": "Up over the last 6 months",
    "squeeze": "Volatility squeezed (20-day vs 120-day)",
}
PATTERNS = {
    "new_high_3m": "New 3-month high today (breakout through resistance)",
    "new_low_3m": "New 3-month low today (break below support)",
    "support_bounce": "Bounce off support (3-month low in the last 10 days, within 5% of it, up over 5 days)",
    "golden_cross_event": "Golden cross in the last month",
    "death_cross_event": "Death cross in the last month",
    "rsi_under_30": "RSI under 30 (oversold)",
    "rsi_over_70": "RSI over 70 (overbought)",
    "below_lower_band": "Below the lower Bollinger band",
    "above_upper_band": "Above the upper Bollinger band",
    "above_200dma_flag": "Above its 200-day average",
}


def _rsi(px, n=14):
    d = px.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100 / (1 + up / dn)          # no down days = 100; a flat stock (0/0) = missing


def panels(px, dates):
    """{indicator or pattern: DataFrame on the sample dates}. Each is built from closes up to that day only and
    trimmed to the sample dates at once, so the full daily frames never pile up in memory."""
    idx = px.index[px.index.isin(pd.to_datetime(list(dates)))]
    out = {}

    def keep(name, frame):
        out[name] = frame.loc[idx].replace([np.inf, -np.inf], np.nan)

    ma50, ma200 = px.rolling(50).mean(), px.rolling(200).mean()
    keep("above_200dma", px / ma200 - 1)
    keep("above_50dma", px / ma50 - 1)
    keep("golden_cross", ma50 / ma200 - 1)
    keep("ma50_slope", ma50 / ma50.shift(21) - 1)
    keep("golden_cross_event", (ma50 > ma200) & (ma50.shift(21) <= ma200.shift(21)))
    keep("death_cross_event", (ma50 < ma200) & (ma50.shift(21) >= ma200.shift(21)))
    keep("above_200dma_flag", px > ma200)
    hi63, lo63p = px.shift(1).rolling(63).max(), px.shift(1).rolling(63).min()
    keep("breakout_3m", px / hi63 - 1)
    keep("new_high_3m", px > hi63)
    keep("new_low_3m", px < lo63p)
    lo63 = px.rolling(63).min()
    keep("near_support", -(px / lo63 - 1))
    keep("support_bounce", (px / lo63 - 1 <= 0.05) & (px / px.shift(5) - 1 > 0) & (px.rolling(10).min() <= lo63 * 1.0000001))
    keep("above_52w_low", px / px.rolling(252).min() - 1)
    del ma50, ma200, hi63, lo63p, lo63
    rsi = _rsi(px)
    keep("rsi_oversold", -rsi)
    keep("rsi_under_30", rsi < 30)
    keep("rsi_over_70", rsi > 70)
    del rsi
    ma20, sd20 = px.rolling(20).mean(), px.rolling(20).std()
    pctb = (px - (ma20 - 2 * sd20)) / (4 * sd20).replace(0, np.nan)
    keep("bollinger_low", -pctb)
    keep("below_lower_band", pctb < 0)
    keep("above_upper_band", pctb > 1)
    del ma20, sd20, pctb
    lo14, hi14 = px.rolling(14).min(), px.rolling(14).max()
    keep("stochastic_low", -((px - lo14) / (hi14 - lo14).replace(0, np.nan)))
    macd = px.ewm(span=12, adjust=False, min_periods=26).mean() - px.ewm(span=26, adjust=False, min_periods=26).mean()
    keep("macd_hist", (macd - macd.ewm(span=9, adjust=False, min_periods=9).mean()) / px)
    del lo14, hi14, macd
    for name, n in (("roc_1m", 21), ("roc_3m", 63), ("roc_6m", 126)):
        keep(name, px / px.shift(n) - 1)
    ret = px.pct_change(fill_method=None)
    keep("squeeze", -(ret.rolling(20).std() / ret.rolling(120).std().replace(0, np.nan)))
    return out


def attach(df, pan):
    """The samples with a ta_<name> column per indicator and a pat_<name> column per pattern."""
    df = df.copy()
    key = pd.MultiIndex.from_arrays([pd.to_datetime(df["date"]), df["ticker"]])
    for name, frame in pan.items():
        col = ("ta_" if name in INDICATORS else "pat_") + name
        s = frame.stack(future_stack=True)
        v = s.reindex(key).to_numpy()
        df[col] = v.astype(float) if name in INDICATORS else pd.Series(v).fillna(False).astype(bool).to_numpy()
    return df


def _stat(s, annual=False):
    s = s.dropna()
    if len(s) < 12:
        return {"mean": None, "t": None}
    se = s.std(ddof=1) / np.sqrt(len(s))
    k = 12 if annual else 1
    return {"mean": round(float(s.mean() * k), 4), "t": round(float(s.mean() / se), 2) if se > 0 else None,
            "lo": round(float((s.mean() - 1.96 * se) * k), 4), "hi": round(float((s.mean() + 1.96 * se) * k), 4)}


def r_all(df):
    return df["resid"].clip(-st.RETURN_CAP, st.RETURN_CAP)


def run(df, px, spy, current_w):
    """df: the screen backtest's samples (with fwd). Returns the results dict."""
    months = sorted(df["date"].unique())
    df = attach(df, panels(px, months))
    names = [n for n in INDICATORS if df[f"ta_{n}"].notna().any()]
    sig = {**{n: (f"ta_{n}", 1) for n in names}, **st.history.SIGNALS}
    df, all_names = st.add_scores(df, sig)
    mid, start = months[len(months) // 2], months[st.WARMUP_MONTHS]
    ics = st.monthly_ic(df, names)

    # ---- each indicator alone (all months; halves; a portfolio built on it alone)
    alone = {}
    for n in names:
        m = st.evaluate(df, df[f"s_{n}"], spy)
        alone[n] = {"label": INDICATORS[n], "ic": _stat(ics[n]), "first_half": _stat(ics.loc[ics.index < mid, n]),
                    "second_half": _stat(ics.loc[ics.index >= mid, n]),
                    "top_vs_universe": _stat(m["top_vs_universe"], annual=True), "turnover": round(float(m["turnover"].mean()), 3)}

    # ---- yes/no patterns: what the stocks showing one did next (vs their sector, capped moves)
    r = df["resid"].clip(-st.RETURN_CAP, st.RETURN_CAP)
    pats = {}
    for n, label in PATTERNS.items():
        f = df[f"pat_{n}"]
        by = r[f].groupby(df["date"][f]).mean()
        pats[n] = {"label": label, "share": round(float(f.mean()), 3), "all": _stat(by, annual=True),
                   "first_half": _stat(by[by.index < mid], annual=True), "second_half": _stat(by[by.index >= mid], annual=True)}

    # ---- as a screen-out rule: drop the worst (or the most stretched) tenth by each indicator, or every stock
    # showing a pattern. What did the dropped stocks do next, and what happens to the current screen's
    # top-2-per-sector portfolio when it may never buy them (out-of-sample months)?
    test = df[df["date"] >= start].copy()
    cur0 = {k: v for k, v in current_w.items() if k in all_names and v > 0}
    comp0 = st.composite(test, cur0)
    base0 = st._top_excess(test, comp0, None)
    rules = {}
    for n in names:
        rk = df[f"ta_{n}"].groupby([df["date"], df["sector"]]).rank(pct=True)
        rules[f"{INDICATORS[n]}: the LEAST so (bottom tenth)"] = (rk <= 0.10) & df[f"ta_{n}"].notna()
        rules[f"{INDICATORS[n]}: the MOST so (top tenth)"] = (rk > 0.90) & df[f"ta_{n}"].notna()
    for n, label in PATTERNS.items():
        rules[label] = df[f"pat_{n}"]
    screen_out = {}
    for label, f in rules.items():
        by = r_all(df)[f].groupby(df["date"][f]).mean()
        d = (st._top_excess(test, comp0, f.reindex(test.index)) - base0).dropna()
        se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 2 else 0
        screen_out[label] = {"share": round(float(f.mean()), 3), "dropped": _stat(by, annual=True),
                             "first_half": _stat(by[by.index < mid], annual=True), "second_half": _stat(by[by.index >= mid], annual=True),
                             "portfolio_gain": {"mean": round(float(d.mean() * 12), 4), "t": round(float(d.mean() / se), 2) if se > 0 else None}}

    # ---- together, out of sample
    wf = st.walk_forward(df, names, ics, start)
    cur = {k: v for k, v in current_w.items() if k in all_names and v > 0}
    base = st.composite(test, cur)

    def yearly(key):
        s = pd.Series(np.nan, index=test.index)
        for y, w in wf.items():
            i = test.index[test["date"].str[:4] == y]
            s.loc[i] = st.composite(test.loc[i], w[key])
        return s

    ridge = yearly("wf_ridge")
    mixes = {"current": base, "ta_equal": st.composite(test, {n: 1.0 for n in names}), "ta_wf_ic": yearly("wf_ic"),
             "ta_ridge": ridge, "current_plus_ta": (1 - BLEND) * base + BLEND * ridge}
    monthly = {k: st.evaluate(test, v, spy) for k, v in mixes.items()}
    return {"built": now_et().date().isoformat(), "first_month": months[0], "last_month": months[-1], "split_at": mid,
            "first_test_month": start, "indicators": names, "alone": alone, "patterns": pats,
            "together": {k: st.summary(m) for k, m in monthly.items()},
            "vs_current": {k: {"ic": st.paired(m, monthly["current"]),
                               "top_vs_universe": st.paired(m, monthly["current"], "top_vs_universe")}
                           for k, m in monthly.items() if k != "current"},
            "latest_ridge_weights": {k: round(v, 4) for k, v in sorted(wf[max(wf)]["wf_ridge"].items(), key=lambda kv: -kv[1]) if v > 0},
            "screen_out": screen_out, "tests": len(names) + len(PATTERNS)}


LABEL = {"current": "Current screen", "ta_equal": "Technical only: all indicators, equal parts",
         "ta_wf_ic": "Technical only: walk-forward, by past IC", "ta_ridge": "Technical only: walk-forward ridge",
         "current_plus_ta": f"Current screen + technical ridge at {BLEND * 100:.0f}%"}


def report(res):
    pct = st.pct
    L = [f"# Technical-indicator backtest ({res['built']})", "",
         f"Month-ends {res['first_month']} to {res['last_month']}; every indicator uses closing prices up to that day only "
         f"and is scored in the direction chartists read as bullish. Target: the next 4 weeks against the stock's sector. "
         f"With {res['tests']} indicators and patterns tried, a t beyond about 3 either way is the bar for one alone; "
         f"a real effect should also keep its sign in both halves (split at {res['split_at']}).", "",
         "## Each indicator alone", "",
         "| Indicator (bullish reading) | IC | t | First half t | Second half t | Top-2-per-sector vs universe, a year | t | Monthly turnover |",
         "|---|---|---|---|---|---|---|---|"]
    for n, v in sorted(res["alone"].items(), key=lambda kv: -(kv[1]["ic"]["t"] or 0)):
        L.append(f"| {v['label']} | {v['ic']['mean']:+.4f} | {v['ic']['t']} | {v['first_half']['t']} | {v['second_half']['t']} | "
                 f"{pct(v['top_vs_universe']['mean'])} | {v['top_vs_universe']['t']} | {v['turnover'] * 100:.0f}% |")
    L += ["", "A negative IC means the bullish reading pointed the wrong way: those stocks went on to lag.", "",
          "## Patterns: what stocks showing one did next (vs their sector, a year)", "",
          "| Pattern | Share of stock-months | All years | t | First half | t | Second half | t |", "|---|---|---|---|---|---|---|---|"]
    for n, v in sorted(res["patterns"].items(), key=lambda kv: -(kv[1]["all"]["t"] or 0)):
        L.append(f"| {v['label']} | {v['share'] * 100:.0f}% | {pct(v['all']['mean'])} | {v['all']['t']} | {pct(v['first_half']['mean'])} | "
                 f"{v['first_half']['t']} | {pct(v['second_half']['mean'])} | {v['second_half']['t']} |")
    so = res.get("screen_out") or {}
    if so:
        L += ["", "## As a screen-out rule", "",
              f"Each rule drops a group of stocks every month: the bottom or top tenth of an indicator inside each sector, or "
              f"every stock showing a pattern. 'Dropped stocks' is what they earned against their sector over the next 4 "
              f"weeks, a year: a useful rule drops stocks that went on to LAG (clearly negative, in both halves). The last "
              f"columns are what the current screen's top-2-per-sector portfolio gained when it could never buy them. "
              f"With {len(so)} rules tried, a t beyond about 3.2 is the bar for one alone.", "",
              "| Rule: never buy... | Share dropped | Dropped stocks, a year | t | First half t | Second half t | Portfolio gain, a year | t |",
              "|---|---|---|---|---|---|---|---|"]
        for k, v in sorted(so.items(), key=lambda kv: (kv[1]["dropped"]["t"] is None, kv[1]["dropped"]["t"] or 0)):
            L.append(f"| {k} | {v['share'] * 100:.0f}% | {pct(v['dropped']['mean'])} | {v['dropped']['t']} | {v['first_half']['t']} | "
                     f"{v['second_half']['t']} | {pct(v['portfolio_gain']['mean'], 2)} | {v['portfolio_gain']['t']} |")
    L += ["", f"## Together (out of sample from {res['first_test_month']})", "",
          "| Mix | IC | t | Top-2-per-sector vs universe, a year | 95% range | t | After costs | Monthly turnover |",
          "|---|---|---|---|---|---|---|---|"]
    for k, s in res["together"].items():
        L.append(f"| {LABEL[k]} | {s['ic']['mean']:+.4f} | {s['ic']['t']} | {pct(s['top_vs_universe']['mean'])} | "
                 f"{pct(s['top_vs_universe'].get('lo'))} to {pct(s['top_vs_universe'].get('hi'))} | {s['top_vs_universe']['t']} | "
                 f"{pct(s.get('net_vs_universe'))} | {s['turnover'] * 100:.0f}% |")
    L += ["", "| Against the current screen | IC difference | t | Portfolio difference, a month | t |", "|---|---|---|---|---|"]
    for k, v in res["vs_current"].items():
        L.append(f"| {LABEL[k]} | {v['ic']['diff']:+.4f} | {v['ic']['t']} | {pct(v['top_vs_universe']['diff'], 2)} | {v['top_vs_universe']['t']} |")
    w = res["latest_ridge_weights"]
    tot = sum(w.values()) or 1
    L += ["", "Latest walk-forward ridge weights: " + (", ".join(f"{k} {v / tot * 100:.0f}%" for k, v in w.items()) or "none positive") + ".", "",
          "## Limits", "",
          "- Closing prices only: no volume, no daily highs or lows.",
          "- Today's index members only, month-end decisions, a 4-week hold, no trading costs except in the after-costs column.",
          "- Support and resistance here are rule-based (3-month highs and lows), not hand-drawn chart levels."]
    return "\n".join(L) + "\n"


def chart(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = sorted(res["alone"].items(), key=lambda kv: -(kv[1]["ic"]["mean"] or 0))
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(rows) + 1.6))
    for i, (n, v) in enumerate(rows):
        s = v["ic"]
        strong = abs(s["t"] or 0) >= 3
        c = "#2a78d6" if strong else "#6b6b66"
        ax.plot([s["lo"], s["hi"]], [i, i], color=c, lw=2, alpha=0.5)
        ax.plot(s["mean"], i, "o", color=c, ms=7)
        ax.annotate(f"t {s['t']:+.1f}", (s["hi"], i), xytext=(6, -4), textcoords="offset points", fontsize=9, color="#333")
    ax.axvline(0, color="#999", lw=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([v["label"] for _, v in rows], fontsize=9)
    ax.invert_yaxis()
    ax.set_title("Technical indicators alone: correlation with the next 4 weeks (IC, 95% range)\n"
                 "Right of zero = the bullish reading worked. Blue = clears the bar (none do if all grey)",
                 fontsize=10, loc="left")
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
