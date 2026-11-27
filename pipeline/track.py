"""
TRACKING  —  run:  python -m pipeline.track   (weekly, after the screen; monthly email)

 1. Reconcile    record trades ticked on the checklist (rebuild plan after 4+ days; watch sells)
 2. Portfolios   daily value since inception for:
                   AI actual            replayed from your recorded trades (and after AI costs)
                   AI as recommended    every rebuild's target, as if placed at the trade-date close
                   Screen-only control  the free quant screen's portfolio, same cadence and rules
                   SPY, SPTM            buy and hold
 3. Metrics      returns (since inception, 1/3/6 months), volatility, worst drawdown, Sharpe,
                 after-cost and estimated after-tax (Individual account) results
 4. Attribution  sector choices (macro agent) vs stock picks (stock team), plus picks by size tier
 5. Scorecards   debate winners, each screen signal, macro predictions; plus the judge report card
                 (ledger.py): every judged stock graded vs its equal-weighted sector at 2/4/13 weeks
                 Controls: equal-weight same picks, top-rated with no PM/macro, sector-ETF portfolios
                 for the macro tilts vs the free momentum rule
 6. Drawdown     AI actual vs SPY over rolling 3 months -> level 0/1/2 for the portfolio manager
 7. Robinhood    optional cross-check against CSV exports placed in imports/robinhood/
 8. Email        monthly report with chart; immediate alert if the drawdown level changes
"""
import glob
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from . import config
from . import ledger
from .book import load_book, reconcile_all, trade_log
from .notify import send, subject_line
from .runner import run_stage
from .util import append_csv, now_et, read_json, require_columns, state_path, write_json

TODAY = now_et().date()
FWD_DAYS = 10                    # a rebuild period, in trading days
LEVEL1, LEVEL2, RECOVER = -0.05, -0.10, -0.025


# ==================================================================== recording (called by rebuild)
def control_portfolios(team_res, weights, parking="SPY"):
    """Two controls that isolate what each part of the process adds:
    equal_weight  the same stocks the PM chose, equal weights (does sizing add anything?)
    no_macro      the team's top-rated stocks, same count, equal weight, no sector limits and no
                  PM (do the macro tilts and the PM add anything over the judges alone?)"""
    names = [t for t, w in weights.items() if t != parking and w > 0]
    stock_total = sum(weights[t] for t in names)
    eq = {t: round(stock_total / len(names), 3) for t in names} if names else {}
    if weights.get(parking):
        eq[parking] = weights[parking]
    st = team_res["stocks"]
    from .pm import eligible_new
    ranked = sorted((t for t, s in st.items() if eligible_new(s)),
                    key=lambda t: (-st[t]["verdict"].get("edge_pts", 0), -st[t].get("composite", 0)))
    top = ranked[:max(len(names), 1)] if ranked else []
    nm = {t: round(100 / len(top), 3) for t in top} if top else {parking: 100}
    return eq, nm


def record_rebuild(plan, team_res, candidates, weights):
    hist = [h for h in read_json(state_path("rebuild_history.json"), []) if h.get("trade_date") != plan["trade_date"]]
    vh = state_path("verdict_history.csv")
    if vh.exists():                            # a replan replaces the earlier plan for the same trade date
        old = pd.read_csv(vh, dtype={"date": str})
        old[old.date != str(plan["trade_date"])].to_csv(vh, index=False)
    control = {c["ticker"]: c["weight_%"] for c in (candidates or {}).get("control_portfolio", [])}
    eq, nm = control_portfolios(team_res, weights)
    hist.append({"date": plan["date"], "trade_date": plan["trade_date"], "team_date": team_res.get("date"),
                 "target": weights, "control": control, "equal_weight": eq, "no_macro": nm,
                 "paper": bool(plan.get("paper")), "versions": plan.get("versions"),
                 "sectors": {t: s["sector"] for t, s in team_res["stocks"].items()}})
    write_json(state_path("rebuild_history.json"), hist)
    append_csv(state_path("verdict_history.csv"), [
        {"date": plan["trade_date"], "team_date": team_res.get("date"), "ticker": t, "conviction": s["verdict"]["conviction"],
         "probability": s["verdict"].get("probability"), "edge_pts": s["verdict"].get("edge_pts"),
         "winner": s["verdict"].get("winner"), "composite": round(s["composite"], 4), "in_portfolio": t in weights}
        for t, s in team_res["stocks"].items()])


# ==================================================================== prices
def closes(tickers, start):
    import yfinance as yf
    tickers = sorted(set(tickers))
    d = yf.download([t.replace(".", "-") for t in tickers], start=start, progress=False, auto_adjust=True)["Close"]
    if isinstance(d, pd.Series):
        d = d.to_frame(tickers[0])
    d.columns = [c.replace("-", ".") for c in d.columns]
    return require_columns(d.sort_index(), ["SPY"] if "SPY" in tickers else [], "tracking")


# ==================================================================== portfolios
def nav_from_schedule(schedule, px, start_value):
    """schedule: [(date, {ticker: weight%})]. Rebalance at the close of the first trading day on/after each date."""
    if not schedule:
        return pd.Series(dtype=float)
    days = px.index[px.index >= pd.Timestamp(schedule[0][0])]
    sched = {}
    for d, w in schedule:
        i = px.index.searchsorted(pd.Timestamp(d))
        if i < len(px.index):
            sched[px.index[i]] = w
    shares, cash, out = {}, start_value, {}
    for day in days:
        prices = px.loc[day]
        value = cash + sum(n * prices.get(t, np.nan) for t, n in shares.items() if pd.notna(prices.get(t, np.nan)))
        if day in sched:
            w = {t: x for t, x in sched[day].items() if pd.notna(prices.get(t, np.nan))}
            shares = {t: value * x / 100 / prices[t] for t, x in w.items()}
            cash = value - sum(value * x / 100 for x in w.values())
        out[day] = cash + sum(n * prices[t] for t, n in shares.items() if pd.notna(prices.get(t, np.nan)))
    return pd.Series(out)


def nav_actual(log, px, start_value):
    if log is None or not len(log):
        return pd.Series(dtype=float)
    log = log.assign(date=pd.to_datetime(log.date)).sort_values("date")
    shares, cash, out = {}, start_value, {}
    for day in px.index[px.index >= log.date.min()]:
        for _, t in log[log.date == day].iterrows():
            n = float(t.shares)
            if t.action == "BUY":
                shares[t.ticker] = shares.get(t.ticker, 0) + n
                cash -= float(t.amount)
            else:
                shares[t.ticker] = shares.get(t.ticker, 0) - n
                cash += float(t.amount)
        p = px.loc[day]
        out[day] = cash + sum(n * p.get(tk, np.nan) for tk, n in shares.items() if abs(n) > 1e-9 and pd.notna(p.get(tk, np.nan)))
    return pd.Series(out)


def metrics(nav):
    nav = nav.dropna()
    if len(nav) < 2:
        return {}
    r = nav.pct_change().dropna()
    per = lambda n: round((nav.iloc[-1] / nav.iloc[-n - 1] - 1) * 100, 2) if len(nav) > n else None
    return {"since_inception_%": round((nav.iloc[-1] / nav.iloc[0] - 1) * 100, 2), "1m_%": per(21), "3m_%": per(63),
            "6m_%": per(126), "volatility_%": round(r.std() * np.sqrt(252) * 100, 1) if len(r) > 5 else None,
            "max_drawdown_%": round((nav / nav.cummax() - 1).min() * 100, 2),
            "sharpe": round(r.mean() / r.std() * np.sqrt(252), 2) if len(r) > 20 and r.std() > 0 else None,
            "value": round(float(nav.iloc[-1]), 2), "days": len(nav)}


def cost_series(index):
    p = state_path("cost_log.csv")
    if not p.exists() or not len(index):
        return pd.Series(0.0, index=index)
    c = pd.read_csv(p)
    c = c.groupby(pd.to_datetime(c.date)).cost.sum().cumsum()
    return c.reindex(index.union(c.index)).ffill().fillna(0).reindex(index)


def after_tax_drag():
    log = trade_log()
    if not len(log) or "realized_gain" not in log:
        return 0.0
    ind = log[(log.account == "individual") & (log.action == "SELL")]
    term = ind["term"] if "term" in ind else pd.Series("short", index=ind.index)
    short = float(ind[term.fillna("short") != "long"].realized_gain.sum())
    long_ = float(ind[term.fillna("short") == "long"].realized_gain.sum())
    if short < 0:                         # losses offset gains of the other kind first
        long_, short = long_ + short, 0.0
    if long_ < 0:
        short, long_ = short + long_, 0.0
    return round(max(0.0, short) * config.TAX_RATE_SHORT_TERM + max(0.0, long_) * config.TAX_RATE_LONG_TERM, 2)


# ==================================================================== attribution
def attribution(hist, px, bench):
    """Per rebuild period: allocation = sum_s w_s * R(sector ETF) - R(SPY)  (macro agent's sector bets)
                           selection  = sum_i w_i * (R_i - R(its sector ETF))  (stock team's picks)"""
    rows = []
    etf = config.SECTORS
    idx_of = bench["index"].to_dict() if "index" in bench else {}
    for k, h in enumerate(hist):
        a = px.index.searchsorted(pd.Timestamp(h["trade_date"]))
        b = px.index.searchsorted(pd.Timestamp(hist[k + 1]["trade_date"])) if k + 1 < len(hist) else len(px.index) - 1
        if a >= len(px.index) or b <= a:
            continue
        ret = (px.iloc[b] / px.iloc[a] - 1)
        spy = ret.get("SPY", np.nan)
        alloc, sel, tiers = 0.0, 0.0, {}
        for t, w in h["target"].items():
            w = w / 100
            if t == "SPY" or pd.isna(ret.get(t, np.nan)):
                alloc += w * spy if t == "SPY" else 0
                continue
            s = h["sectors"].get(t) or (bench.loc[t, "sector"] if t in bench.index else None)
            r_s = ret.get(etf.get(s, "SPY"), spy)
            alloc += w * r_s
            contrib = w * (ret[t] - r_s)
            sel += contrib
            tier = idx_of.get(t, "other")
            tiers[tier] = tiers.get(tier, 0) + contrib
        rows.append({"period_start": str(px.index[a].date()), "portfolio_%": round((alloc + sel) * 100, 2),
                     "spy_%": round(spy * 100, 2), "allocation_%": round((alloc - spy) * 100, 2),
                     "selection_%": round(sel * 100, 2), **{f"selection_{k}_%": round(v * 100, 2) for k, v in tiers.items()}})
    return rows


# ==================================================================== scorecards
def fwd_excess(px, ticker, date, days=FWD_DAYS):
    i = px.index.searchsorted(pd.Timestamp(date))
    if ticker not in px or i + days >= len(px.index):
        return np.nan
    a, b = px[ticker].iloc[i], px[ticker].iloc[i + days]
    sa, sb = px["SPY"].iloc[i], px["SPY"].iloc[i + days]
    return (b / a - 1) - (sb / sa - 1) if pd.notna(a) and pd.notna(b) else np.nan


def scorecards(px):
    out = {}
    p = state_path("verdict_history.csv")
    if p.exists():
        v = pd.read_csv(p)
        v["excess"] = [fwd_excess(px, t, d) for t, d in zip(v.ticker, v.date)]
        g = v.dropna(subset=["excess"])
        if len(g):
            out["by_conviction"] = {int(c): {"avg_excess_%": round(x.excess.mean() * 100, 2), "n": len(x)} for c, x in g.groupby("conviction")}
            out["by_debate_winner"] = {w: {"avg_excess_%": round(x.excess.mean() * 100, 2), "n": len(x)} for w, x in g.groupby("winner")}
            hi, mid = g[g.conviction >= 4].excess, g[g.conviction == 3].excess
            rebuilds = g.date.nunique()
            ready = rebuilds >= 6 and len(g) >= 40 and len(hi) and len(mid) and hi.mean() - mid.mean() >= 0.01
            out["conviction_weighting"] = ("RECOMMENDED: conviction 4-5 picks beat 3s by "
                                           f"{(hi.mean() - mid.mean()) * 100:.1f} pts per period over {rebuilds} rebuilds"
                                           if ready else f"not yet ({rebuilds} graded rebuilds, {len(g)} picks; need 6 and 40 with a 1-pt edge)")
    sig = read_json(state_path("signal_history.json"), {})
    spreads = {}
    for d, sigs in sig.items():
        for name, tb in sigs.items():
            top = np.nanmean([fwd_excess(px, t, d, 5) for t in tb["top"]]) if tb["top"] else np.nan
            bot = np.nanmean([fwd_excess(px, t, d, 5) for t in tb["bottom"]]) if tb["bottom"] else np.nan
            if pd.notna(top) and pd.notna(bot):
                spreads.setdefault(name, []).append(top - bot)
    if spreads:
        out["signal_spread_1wk_%"] = {k: {"avg_%": round(np.mean(v) * 100, 2), "weeks": len(v),
                                           "positive_weeks_%": round(np.mean([x > 0 for x in v]) * 100)} for k, v in spreads.items()}
    ev = read_json(state_path("signal_evidence.json"))
    if ev:
        from .screen import signal_verdicts
        out["screen_signals_15yr"] = {k: dict(v, verdict=signal_verdicts(ev).get(k)) for k, v in ev.get("signals", {}).items()}
    mp = state_path("macro_predictions.csv")
    if mp.exists():
        m = pd.read_csv(mp, dtype=str)
        done = m[m.status.isin(["hit", "miss"])]
        out["macro_predictions"] = {"graded": len(done), "hit_rate_%": round((done.status == "hit").mean() * 100, 1) if len(done) else None}
    return out


# ==================================================================== drawdown rule
def drawdown_level(ai, spy):
    st = read_json(state_path("drawdown.json"), {"level": 0})
    both = pd.concat([ai, spy], axis=1).dropna()
    if len(both) < 10:
        return st, False
    rel = (both.iloc[:, 0] / both.iloc[0, 0]) / (both.iloc[:, 1] / both.iloc[0, 1])
    rel = rel.tail(63)
    dd = float(rel.iloc[-1] / rel.max() - 1)
    old = st.get("level", 0)
    new = 2 if dd <= LEVEL2 else 1 if dd <= LEVEL1 else (0 if dd > RECOVER else old)
    st = {"level": new, "relative_drawdown_%": round(dd * 100, 2), "as_of": TODAY.isoformat()}
    write_json(state_path("drawdown.json"), st)
    return st, new != old


# ==================================================================== Alpaca paper cross-check
def alpaca_check(book):
    """Paper mode with Alpaca: does the Alpaca paper account hold what the book says? (Only once every
    placed order has been recorded, so an in-flight order isn't reported as a difference.)"""
    from . import broker
    if not broker.enabled():
        return []
    try:
        from .book import adhoc_plan_files
        for pf in ["pending_plan.json"] + adhoc_plan_files():
            plan = read_json(state_path(pf))
            if plan and plan.get("broker") and not plan.get("reconciled"):
                return []
        return [f"Alpaca paper {x}" for x in broker.position_diff(book)]
    except Exception as e:
        return [f"Alpaca paper check unavailable ({str(e)[:80]})"]


# ==================================================================== Robinhood cross-check
def robinhood_check(book):
    """Optional: put Robinhood account activity CSVs in imports/robinhood/, with 'individual' or 'ira'
    in the file name. Net shares from Buy/Sell rows are compared with the book."""
    from .config import ROOT
    notes = []
    for f in glob.glob(str(ROOT / "imports" / "robinhood" / "*.csv")):
        acct = "ira" if "ira" in f.lower() else "individual"
        try:
            df = pd.read_csv(f, on_bad_lines="skip")
        except Exception as e:
            notes.append(f"{f}: unreadable ({e})")
            continue
        cols = {c.lower().strip(): c for c in df.columns}
        inst, code, qty = cols.get("instrument"), cols.get("trans code"), cols.get("quantity")
        if not (inst and code and qty):
            notes.append(f"{f}: expected Instrument / Trans Code / Quantity columns")
            continue
        df[qty] = pd.to_numeric(df[qty].astype(str).str.replace(",", "").str.extract(r"([\d.]+)")[0], errors="coerce")
        sign = df[code].astype(str).str.lower().map({"buy": 1, "sell": -1})
        net = (df[qty] * sign).groupby(df[inst]).sum()
        mine = {p["ticker"]: p["shares"] for p in book["positions"] if p["account"] == acct}
        for t in set(net.index) | set(mine):
            a, b = float(net.get(t, 0) or 0), float(mine.get(t, 0))
            if abs(a - b) > 0.01:
                notes.append(f"{acct} {t}: Robinhood {a:.4f} shares vs book {b:.4f}")
    return notes


# ==================================================================== report + email
def chart(navs, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for name, s in navs.items():
        s = s.dropna()
        if len(s) > 1:
            ax.plot(s.index, (s / s.iloc[0] - 1) * 100, label=name, linewidth=2.2 if name.startswith("AI actual") else 1.2)
    ax.axhline(0, color="gray", linewidth=0.6)
    ax.set_ylabel("% since start")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def status_line():
    s = read_json(state_path("performance.json"), {})
    m = s.get("metrics", {})
    ai, spy = m.get("AI actual (after AI costs)", {}), m.get("SPY", {})
    if not ai or not spy:
        return ""
    diff = ai.get("since_inception_%", 0) - spy.get("since_inception_%", 0)
    return (f"AI portfolio {ai['since_inception_%']:+.1f}% vs SPY {spy['since_inception_%']:+.1f}% since inception, "
            f"after AI costs ({diff:+.1f} pts)")


def decision_checkpoint(days, m):
    if days < 120:
        return f"Review checkpoint: 6-month review in about {max(0, 126 - days) // 21 + 1} months."
    ai, ctl, spy = (m.get(k, {}).get("since_inception_%") for k in ("AI actual (after AI costs)", "Screen-only control", "SPY"))
    if None in (ai, ctl, spy):
        return ""
    verdict = ("beats both SPY and the screen: continue, consider expanding" if ai > spy and ai > ctl else
               "beats SPY but not the screen: the AI stages aren't earning their cost" if ai > spy else
               "trails SPY: pause and rethink the signals")
    return f"{'12' if days >= 250 else '6'}-month checkpoint (decided in advance): AI {ai:+.1f}% vs SPY {spy:+.1f}% vs screen {ctl:+.1f}%. {verdict}."


def report(m, attr, cards, dd, rh, cost_total, tax, checkpoint):
    L = [f"# Performance, {TODAY}", "", "| Portfolio | Since start | 1m | 3m | 6m | Vol | Max DD | Sharpe |", "|---|---|---|---|---|---|---|---|"]
    for k, v in m.items():
        if v:
            L.append(f"| {k} | {v['since_inception_%']:+.2f}% | {v.get('1m_%') or ''} | {v.get('3m_%') or ''} | {v.get('6m_%') or ''} | "
                     f"{v.get('volatility_%') or ''} | {v['max_drawdown_%']}% | {v.get('sharpe') or ''} |")
    L += ["", f"AI costs to date: ${cost_total:.2f}. Estimated tax on realized short-term gains (Individual, at "
              f"{config.TAX_RATE_SHORT_TERM:.0%}): ${tax:.2f}.", f"Drawdown rule: level {dd.get('level', 0)} "
              f"(relative drawdown {dd.get('relative_drawdown_%', 0)}% over 3 months).", "", checkpoint, ""]
    if attr:
        tot = {k: round(sum(r.get(k, 0) for r in attr), 2) for k in attr[-1] if k.endswith("_%")}
        L += ["## Attribution (sum of rebuild periods)", f"- Sector choices (macro agent): {tot.get('allocation_%', 0):+.2f} pts vs SPY",
              f"- Stock picks (stock team): {tot.get('selection_%', 0):+.2f} pts vs their sector ETFs"]
        L += [f"  - {k.replace('selection_', '').replace('_%', '')}: {v:+.2f} pts" for k, v in tot.items() if k.startswith("selection_S")]
    if cards:
        L += ["", "## Scorecards", "```", json.dumps(cards, indent=1), "```"]
    if rh:
        L += ["", "## Brokerage cross-check differences (Robinhood exports / Alpaca paper)"] + [f"- {n}" for n in rh]
    return "\n".join(L)


# ==================================================================== MAIN
def main(session, folder, monthly=None):
    hist = read_json(state_path("rebuild_history.json"), [])
    book = load_book()
    held = [p["ticker"] for p in book["positions"]]
    log = trade_log()
    names = set(held) | set(log.ticker if len(log) else []) | {"SPY", "SPTM"} | set(config.SECTORS.values())
    for h in hist:
        names |= set(h["target"]) | set(h["control"]) | set(h.get("equal_weight") or {}) | set(h.get("no_macro") or {})
    names |= ledger.tickers_needed()
    bench = pd.read_csv(state_path("bench.csv")) if state_path("bench.csv").exists() else pd.DataFrame(columns=["ticker", "sector"])
    sector_of = dict(zip(bench.ticker, bench.sector))
    if ledger.pending():                  # the equal-weighted sector benchmark needs every bench stock
        names |= set(bench.ticker)
    starts = [pd.Timestamp(hist[0]["trade_date"])] if hist else [pd.Timestamp(TODAY - timedelta(days=30))]
    led = state_path("decision_ledger.csv")
    if led.exists():
        starts.append(pd.Timestamp(pd.read_csv(led, usecols=["date"]).date.min()))
    macro_runs = read_json(state_path("macro_etf_history.json"), [])
    if macro_runs:
        starts.append(pd.Timestamp(macro_runs[0]["date"]))
    start = (min(starts) - timedelta(days=10)).date().isoformat()
    px = closes(names, start)
    last = {t: float(px[t].dropna().iloc[-1]) for t in px.columns if px[t].notna().any()}

    print("1/6 Reconciling checklists...")
    recon = reconcile_all(last, min_age_days=4)
    for r in recon:
        print("    " + r)
    book, log = load_book(), trade_log()
    if not hist:
        print("    No rebuilds yet: nothing to track.")
        write_json(state_path("performance.json"), {"date": TODAY.isoformat(), "metrics": {}})
        return {"status": "no history"}

    print("2/6 Portfolios...")
    sv = config.STARTING_VALUE
    inception = hist[0]["trade_date"]
    navs = {"AI actual": nav_actual(log, px, sv),
            "AI as recommended": nav_from_schedule([(h["trade_date"], h["target"]) for h in hist], px, sv),
            "Screen-only control": nav_from_schedule([(h["trade_date"], h["control"]) for h in hist if h["control"]], px, sv),
            "Equal-weight (same picks)": nav_from_schedule([(h["trade_date"], h["equal_weight"]) for h in hist
                                                            if h.get("equal_weight")], px, sv),
            "No-macro (top-rated, no PM)": nav_from_schedule([(h["trade_date"], h["no_macro"]) for h in hist
                                                              if h.get("no_macro")], px, sv),
            "SPY": nav_from_schedule([(inception, {"SPY": 100})], px, sv),
            "SPTM (S&P 1500)": nav_from_schedule([(inception, {"SPTM": 100})], px, sv)}
    if macro_runs:   # sector-ETF portfolios isolate the macro call: the agent's tilts vs the free momentum rule
        navs["Macro tilts (sector ETFs)"] = nav_from_schedule([(r["date"], r["macro"]) for r in macro_runs], px, sv)
        navs["Momentum rule (sector ETFs)"] = nav_from_schedule([(r["date"], r["momentum"]) for r in macro_runs], px, sv)
    if len(navs["AI actual"]):
        navs["AI actual (after AI costs)"] = navs["AI actual"] - cost_series(navs["AI actual"].index)
    m = {k: metrics(v) for k, v in navs.items()}

    print("3/6 Attribution and scorecards...")
    bench = pd.read_csv(state_path("bench.csv")).set_index("ticker") if state_path("bench.csv").exists() else pd.DataFrame()
    attr = attribution(hist, px, bench)
    cards = scorecards(px)
    n_graded = ledger.grade(px, sector_of)
    ev = ledger.evaluate()
    ledger.save(ev)
    print(f"    graded {n_graded} new decision outcomes; decision rule: {(ev.get('rule') or {}).get('verdict', ev.get('status'))}")

    print("4/6 Drawdown rule...")
    ai = navs.get("AI actual (after AI costs)", navs["AI as recommended"])
    dd, changed = drawdown_level(ai, navs["SPY"])

    print("5/6 Saving...")
    cost_total = float(cost_series(pd.DatetimeIndex([pd.Timestamp(TODAY)])).iloc[-1]) if len(ai) else 0.0
    tax = after_tax_drag()
    if "AI actual (after AI costs)" in m and m["AI actual (after AI costs)"]:
        m["AI actual (after costs and est. tax)"] = dict(m["AI actual (after AI costs)"])
        m["AI actual (after costs and est. tax)"]["since_inception_%"] = round(
            (float(ai.iloc[-1]) - tax) / sv * 100 - 100, 2)
    rh = robinhood_check(book) + alpaca_check(book)
    checkpoint = decision_checkpoint(m.get("SPY", {}).get("days", 0), m)
    perf = {"date": TODAY.isoformat(), "inception": inception, "metrics": m, "attribution": attr, "scorecards": cards,
            "drawdown": dd, "ai_cost_total": round(cost_total, 2), "est_tax": tax, "robinhood_differences": rh,
            "evaluation_rule": ev.get("rule")}
    write_json(state_path("performance.json"), perf)
    write_json(folder / "performance.json", perf)
    pd.DataFrame(navs).to_csv(state_path("nav_history.csv"))
    (folder / "report.md").write_text(report(m, attr, cards, dd, rh, cost_total, tax, checkpoint) + "\n\n" + ledger.render_md(ev))

    print("6/6 Email...")
    prev = read_json(state_path("monthly_email.json"), {})
    monthly = monthly if monthly is not None else (TODAY.day <= 7 and prev.get("month") != TODAY.strftime("%Y-%m"))
    if changed:
        send(subject_line("Drawdown rule", "FLAG", f"level {dd['level']}"),
             f"The AI portfolio's 3-month performance relative to SPY is {dd['relative_drawdown_%']}%. Drawdown level is now "
             f"{dd['level']}. At level 1 the next rebuild moves half the stock weight into SPY; at level 2 it moves "
             f"everything to SPY and asks for your review.", save_dir=folder)
    if monthly:
        png = chart(navs, folder / "performance.png")
        rows = "".join(f"<tr><td>{k}</td><td>{v['since_inception_%']:+.2f}%</td><td>{v.get('3m_%') or ''}</td>"
                       f"<td>{v['max_drawdown_%']}%</td></tr>" for k, v in m.items() if v)
        html = (f"<h3>Monthly performance, {TODAY}</h3><p>{status_line()}</p><table border='1' cellpadding='4' "
                f"style='border-collapse:collapse'><tr><th>Portfolio</th><th>Since start</th><th>3m %</th><th>Max DD</th></tr>{rows}</table>"
                f"<p>{checkpoint}</p><p>{cards.get('conviction_weighting', '')}</p>{ledger.render_html(ev)}"
                f"<p>Chart and full report attached.</p>")
        send(subject_line("Monthly performance", "OK", status_line()[:60]), status_line(), html,
             attachments=[p for p in (png, folder / "report.md") if p], save_dir=folder)
        write_json(state_path("monthly_email.json"), {"month": TODAY.strftime("%Y-%m")})
    print(f"    {status_line()}")
    return {"status": "ok"}


if __name__ == "__main__":
    run_stage("track", main)
