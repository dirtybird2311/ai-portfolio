"""
PERFORMANCE AND STATISTICS REPORTS  —  run:  python -m pipeline.report            (daily performance sheet)
                                             python -m pipeline.report --weekly    (adds the statistics report)

Writes reports/performance/latest.html (and a dated copy) plus latest.md, a short text version for email.
Everything is built from the saved NAV files and rebuild history; prices are pulled only for the statistics that
need them (factor proxies; the random-portfolio pools), and a failure there leaves that section marked unavailable
instead of stopping the report.

Daily sheet     paper account (record = adjusted, executed beside it) and the two real accounts against SPY,
                daily lead, last days table.
Weekly report   information ratio and t-stat, block-bootstrap range of the lead, beta and alpha (CAPM and an
                ETF-proxy size/value/momentum regression), max drawdown, the sequential test, where each rebuild's
                picks rank among random portfolios, and the go-live checklist. Every number says how many
                days it rests on.
"""
import base64
import io
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import stats
from .util import now_et, read_json, state_path, private_reports

OUT = "reports/performance"
MIN_FACTOR_DAYS = 20
SPRT_MU1 = 0.0004              # the edge the sequential test looks for: 0.04% a day, about 10% a year
COL = {"record": "#2a78d6", "executed": "#eb6834", "roth": "#1baf7a", "acct2": "#e87ba4", "spy": "#6b6b66"}

# Go-live checklist: thresholds are a proposal (edit here and in GO_LIVE.md); every rule shows its value.
GO_LIVE = {"min_days": 60, "min_rebuilds": 4, "max_p_noise": 0.10, "min_beat_share": 0.90,
           "max_drawdown_ratio": 1.5}


# ==================================================================== data
def _csv(name):
    p = state_path(name)
    return pd.read_csv(p) if p.exists() and p.stat().st_size else pd.DataFrame()


def paper_series():
    """Daily values and returns for the paper account (record and executed) and SPY since the start."""
    d = _csv("daily_account_nav.csv")
    if d.empty:
        return pd.DataFrame()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").set_index("date")
    out = pd.DataFrame({"record": d["record_value"], "executed": d["executed_value"],
                        "spy": d["start_value"] * (1 + d["spy_return_pct"] / 100)})
    out.attrs["start"] = float(d["start_value"].iloc[0])
    return out


def _books():
    return (read_json(state_path("external_books.json"), {}) or {}).get("books", {})


def real_series(name):
    d = _csv(f"daily_nav_{name}.csv")
    if d.empty:
        return pd.DataFrame()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").set_index("date")
    out = pd.DataFrame({"value": d["book_value"], "spy": d["spy_same_dollars_value"]})
    out.attrs["cost"] = float(d["cost"].iloc[-1])
    return out


def combined_real(*books):
    """The real Robinhood accounts as one book: values, SPY-same-dollars and cost add up on the days all have a row."""
    books = [b for b in books if not b.empty]
    if not books:
        return pd.DataFrame()
    out = books[0]
    for b in books[1:]:
        out = out.add(b, fill_value=None).dropna()
    out = out.copy()
    out.attrs["cost"] = float(sum(b.attrs["cost"] for b in books))
    return out


def rets(values, start=None):
    """Daily simple returns of a value series, the first one measured from `start` if given."""
    v = values.dropna()
    r = v.pct_change()
    if start is not None and len(v):
        r.iloc[0] = v.iloc[0] / start - 1
    return r.dropna()


def missing_days(index):
    """Weekdays between the first and last row with no row (holidays show up here too)."""
    if len(index) < 2:
        return []
    want = pd.bdate_range(index.min(), index.max())
    return [d.date().isoformat() for d in want if d not in set(index)]


# ==================================================================== statistics
def factor_frame(loader):
    """ETF-proxy factors: market = SPY; size = IWM-SPY; value = IVE-IVW; momentum = MTUM-SPY (daily returns)."""
    c = loader(["SPY", "IWM", "IVE", "IVW", "MTUM"], None)
    r = c.pct_change().dropna(how="all")
    return pd.DataFrame({"market": r["SPY"], "size": r["IWM"] - r["SPY"], "value": r["IVE"] - r["IVW"],
                         "momentum": r["MTUM"] - r["SPY"]}).dropna()


def paper_stats(ps, loader=None):
    """The statistics block for the paper account's record series."""
    out = {"n_days": 0}
    if ps.empty or len(ps) < 3:
        return out
    start = ps.attrs.get("start")
    rec, spy = rets(ps["record"], start), rets(ps["spy"], start)
    rec, spy = rec.align(spy, join="inner")
    act = rec - spy
    a = stats.active_stats(rec, spy)
    out.update(n_days=len(act), active=a, lead_pts=float((ps["record"].iloc[-1] - ps["spy"].iloc[-1]) / start * 100),
               bootstrap=stats.block_bootstrap(act, block=3),
               sprt=stats.sprt(act, SPRT_MU1),
               capm=stats.capm(rec, spy),
               dd_record=stats.max_drawdown(ps["record"]), dd_spy=stats.max_drawdown(ps["spy"]))
    if len(act) >= MIN_FACTOR_DAYS and loader:
        try:
            out["factors"] = stats.factor_regression(rec, factor_frame(loader))
        except Exception as e:                      # a data failure leaves the section unavailable, never the report
            out["factors_error"] = str(e)[:120]
    return out


def random_tests(loader, now=None, n=5000, full_universe=True):
    """For every rebuild: the picks' return from the trade-date close to the latest close, against random
    portfolios drawn from (A) the judged shortlist with the same number of names per sector and (B) the whole
    screened universe."""
    hist = read_json(state_path("rebuild_history.json"), []) or []
    feats = (read_json(state_path("current_features.json"), {}) or {}).get("stocks", {})
    L1 = "1. Our picks vs random picks from the whole universe"
    L2 = "2. Our picks vs random picks from the shortlist (same sectors)"
    L3 = "3. The whole shortlist vs random stocks from the universe"
    plan = []
    for i, h in enumerate(hist):
        picks = {t: w for t, w in (h.get("target") or {}).items() if t != "SPY" and w > 0}
        if len(picks) < 2:
            continue
        short = sorted(set(h.get("sectors", {})) | set(picks))
        tests = [(L2, picks, short, h.get("sectors"))]
        if full_universe and feats:
            uni = sorted(set(feats) | set(short))
            tests = [(L1, picks, uni, None)] + tests + [(L3, {t: 1.0 for t in short}, uni, None)]
        plan.append((i, h, tests))
    if not plan:
        return []
    # one download for every pool and rebuild (a download per rebuild takes many minutes for ~1,500 tickers)
    allt = sorted({t for _, _, tests in plan for _, _, tick, _ in tests for t in tick})
    first = min(pd.Timestamp(h["trade_date"]) for _, h, _ in plan) - pd.Timedelta(days=5)
    try:
        closes = loader(allt, first).dropna(how="all")
    except Exception as e:
        return [{"rebuild": h["trade_date"], "pool": "all", "ok": False, "why": str(e)[:100]} for _, h, _ in plan]
    rows = []
    for i, h, tests in plan:
        base = pd.Timestamp(h["trade_date"])
        for label, weights, tick, secs in tests:
            try:
                c = closes[[t for t in tick if t in closes.columns]]
                c = c[c.index >= base - pd.Timedelta(days=5)]
                if base not in c.index or len(c) < 2:
                    continue
                r = c.iloc[-1] / c.loc[base] - 1
                days = int((c.index > base).sum())
                if days < 1:
                    continue
                t = stats.random_portfolio_test(weights, r, sectors=secs, n=n, seed=i)
                if t.get("ok"):
                    rows.append({"rebuild": h["trade_date"], "pool": label, "days": days, **t})
            except Exception as e:
                rows.append({"rebuild": h["trade_date"], "pool": label, "ok": False, "why": str(e)[:100]})
    return rows


def checklist(ps_stats, rand_rows, n_rebuilds, nav_missing, frozen_ok, after_cost_lead):
    """Go-live readiness: each rule with its current value. Returns [(rule, value text, status)] and a verdict."""
    G = GO_LIVE
    rule = []
    n = ps_stats.get("n_days", 0)
    rule.append((f"At least {G['min_days']} trading days of record", f"{n} days", n >= G["min_days"]))
    rule.append((f"At least {G['min_rebuilds']} rebuilds", f"{n_rebuilds}", n_rebuilds >= G["min_rebuilds"]))
    b = ps_stats.get("bootstrap", {})
    pn = b.get("p_noise")
    rule.append((f"Lead unlikely to be noise (bootstrap p <= {G['max_p_noise']:.2f})",
                 "n/a" if pn is None else f"p = {pn:.2f}", pn is not None and pn <= G["max_p_noise"]))
    ok = [r for r in rand_rows if r.get("ok") and r["days"] >= 10 and not r["pool"].startswith("3.")]
    med = float(np.median([r["beat_share"] for r in ok])) if ok else None
    rule.append((f"Our picks beat {G['min_beat_share']:.0%} of random portfolios (tests 1 and 2, median over rebuilds with 10+ days)",
                 "n/a (no rebuild has 10+ days)" if med is None else f"{med:.0%}", med is not None and med >= G["min_beat_share"]))
    al = (ps_stats.get("capm") or {})
    alpha = al.get("alpha_annual")
    rule.append(("Alpha against SPY is positive after beta",
                 "n/a" if alpha is None else f"{alpha * 100:+.1f}% a year (beta {al.get('beta', float('nan')):.2f})",
                 alpha is not None and alpha > 0))
    dr = ps_stats.get("dd_record"), ps_stats.get("dd_spy")
    ratio = (dr[0] / dr[1]) if dr[0] is not None and dr[1] else None
    rule.append((f"Drawdown no worse than {G['max_drawdown_ratio']}x SPY's",
                 "n/a" if dr[0] is None else f"{dr[0] * 100:.1f}% vs SPY {dr[1] * 100:.1f}%",
                 dr[0] is not None and (dr[0] >= dr[1] * G["max_drawdown_ratio"] if dr[1] else dr[0] == 0)))
    rule.append(("Still ahead of SPY after AI costs", "n/a" if after_cost_lead is None else f"{after_cost_lead:+.2f} pts",
                 after_cost_lead is not None and after_cost_lead > 0))
    rule.append(("No settings changed without a log entry (freeze log)", "clean" if frozen_ok else "unlogged change", frozen_ok))
    rule.append(("NAV record complete (no missing weekdays)", "complete" if not nav_missing else f"missing {', '.join(nav_missing[:4])}",
                 not nav_missing))
    passed = sum(1 for r in rule if r[2])
    return rule, passed


def verdict(ps_stats):
    n = ps_stats.get("n_days", 0)
    b = ps_stats.get("bootstrap") or {}
    if n < 3 or not b:
        return "Not enough data yet."
    lead = b["observed"] * 100
    pn = b.get("p_noise", float("nan"))
    rng = f"{b['lo'] * 100:+.1f} to {b['hi'] * 100:+.1f} points"
    if n < GO_LIVE["min_days"]:
        return (f"Too early to call. After {n} trading days the paper account is {lead:+.1f} points ahead of SPY "
                f"(a 95% bootstrap range of {rng}); in a world with no skill a lead this large would show up "
                f"about {pn:.0%} of the time. Judge it again at {GO_LIVE['min_days']} days.")
    if pn <= GO_LIVE["max_p_noise"]:
        return f"Evidence is building: {lead:+.1f} points ahead over {n} days, noise explains it only {pn:.0%} of the time."
    return f"No evidence of skill yet: {lead:+.1f} points ahead over {n} days, but noise explains that {pn:.0%} of the time."


# ==================================================================== charts
def _fig_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    import matplotlib.pyplot as plt
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _style(ax, fig, ylabel):
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c2")
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.grid(axis="y", color="#e6e5e0", lw=0.6)
    ax.set_ylabel(ylabel, color="#52514e", fontsize=9)
    ax.axhline(0, color="#9a9992", lw=0.8)


def chart_paper(ps):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.2))
    start = ps.attrs["start"]
    for key, label, ls in (("record", "Paper record (adjusted)", "-"), ("executed", "Paper as executed", "--"),
                           ("spy", "SPY", "-")):
        y = (ps[key] / start - 1) * 100
        ax.plot(ps.index, y, ls, color=COL[key], lw=2, marker="o", ms=3.5)
        ax.annotate(f"{label}\n{y.iloc[-1]:+.2f}%", (ps.index[-1], y.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    fontsize=8, color="#0b0b0b", va="center")
    _style(ax, fig, "% since start")
    ax.margins(x=0.02)
    ax.set_xlim(ps.index[0], ps.index[-1] + pd.Timedelta(days=3.5))
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_png(fig)


def chart_real(real):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = (real["value"] / real.attrs["cost"] - 1) * 100
    ax.plot(real.index, y, color=COL["roth"], lw=2, marker="o", ms=3.5)
    ax.annotate(f"Robinhood (both accounts)\n{y.iloc[-1]:+.2f}%", (real.index[-1], y.iloc[-1]), xytext=(6, 0),
                textcoords="offset points", fontsize=8, color="#0b0b0b", va="center")
    z = (real["spy"] / real.attrs["cost"] - 1) * 100
    ax.plot(real.index, z, color=COL["spy"], lw=2, marker="o", ms=3.5)
    ax.annotate(f"SPY\n{z.iloc[-1]:+.2f}%", (real.index[-1], z.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                fontsize=8, color="#0b0b0b", va="center")
    ax.set_xlim(real.index[0], real.index[-1] + pd.Timedelta(days=3.5))
    _style(ax, fig, "% since entry (Mon Oct 5, 9:30)")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_png(fig)


def chart_active(act):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.bar(act.index, act.values * 100, width=0.7, color=COL["record"])
    _style(ax, fig, "daily lead (pts)")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_png(fig)


def chart_random(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ok = [r for r in rows if r.get("ok")]
    if not ok:
        return None
    fig, ax = plt.subplots(figsize=(8, 0.9 + 0.55 * len(ok)))
    for i, r in enumerate(ok):
        y = len(ok) - i
        ax.plot([r["p5"] * 100, r["p95"] * 100], [y, y], color="#b9b8b0", lw=7, solid_capstyle="butt")
        ax.plot(r["actual"] * 100, y, "o", color=COL["record"], ms=9, mec="#fcfcfb", mew=2)
        ax.text(max(r["p95"], r["actual"]) * 100 + 0.2, y, f"beats {r['beat_share']:.0%}", va="center", fontsize=8)
    ax.set_yticks(range(len(ok), 0, -1))
    ax.set_yticklabels([f"{r['rebuild']}  ({r['days']}d)\n{r['pool']}" for r in ok], fontsize=7.5, color="#52514e")
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors="#52514e", labelsize=8)
    ax.axvline(0, color="#9a9992", lw=0.8)
    ax.set_xlabel("return since the rebuild's trade-date close (%)\nbar = middle 90% of random portfolios, dot = our picks",
                  fontsize=8, color="#52514e")
    fig.tight_layout()
    return _fig_png(fig)


# ==================================================================== page
CSS = """
:root{--bg:#fcfcfb;--card:#fff;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e0;--good:#0a7d3e;--bad:#b3261e;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1a1a19;--card:#232321;--ink:#f0efec;--ink2:#c3c2b7;--line:#3a3a37;--good:#5ccf8a;--bad:#ff8a80;--warn:#e6b450}}
:root[data-theme="dark"]{--bg:#1a1a19;--card:#232321;--ink:#f0efec;--ink2:#c3c2b7;--line:#3a3a37;--good:#5ccf8a;--bad:#ff8a80;--warn:#e6b450}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}p.sub{color:var(--ink2);margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tile b{display:block;font-size:22px}.tile span{color:var(--ink2);font-size:12px}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:8px;font-size:13.5px}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}table.txtlast th:last-child,table.txtlast td:last-child{text-align:left}.scroll{overflow-x:auto}
img{max-width:100%;height:auto;border-radius:8px;border:1px solid var(--line)}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}.note{color:var(--ink2);font-size:13px}
.verdict{background:var(--card);border:1px solid var(--line);border-left:4px solid #2a78d6;border-radius:8px;padding:10px 14px;margin:12px 0}
@media print{:root{--bg:#fff}body{font-size:12px;-webkit-print-color-adjust:exact;print-color-adjust:exact}main{max-width:none;padding:0}
h1,h2{break-after:avoid}img,table,.tiles,.verdict,tr{break-inside:avoid}img{display:block;margin:0 auto;max-width:80%;max-height:105mm;object-fit:contain}h1.break{break-before:page}h2{margin:16px 0 6px}img[alt^='Picks vs random']{max-width:100%;max-height:175mm}
table{font-size:11.5px}.tile b{font-size:19px}}
"""


def _pct(x, d=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.{d}f}%"


def _cls(x):
    return "" if x is None else ("good" if x > 0 else "bad" if x < 0 else "")


def _table(head, rows, text_last=False):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    cls = ' class="txtlast"' if text_last else ""
    return f'<div class="scroll"><table{cls}><tr>{h}</tr>{b}</table></div>'


def build(weekly=False, loader=None, now=None, n_sims=5000):
    """Returns (html, markdown, context). `loader(tickers, start)` returns a DataFrame of closes."""
    now = now or now_et()
    ps = paper_series()
    real = combined_real(*[real_series(k) for k in sorted(_books()) if k.startswith("robinhood_")])
    ctx = {"date": now.date().isoformat(), "weekly": weekly}
    md = [f"# Performance - {ctx['date']}"]
    parts = [f"<h1>Performance</h1><p class='sub'>As of {ctx['date']}. Paper account since "
             f"{ps.index[0].date() if not ps.empty else 'n/a'}; the record is the account as planned (rebuild traded at "
             f"Monday's open), with what actually executed beside it.</p>"]
    if ps.empty:
        parts.append("<p>No NAV rows yet.</p>")
        return _wrap("".join(parts)), "\n".join(md + ["No NAV rows yet."]), ctx
    start = ps.attrs["start"]
    last = ps.iloc[-1]
    rec_r, exe_r, spy_r = [(last[k] / start - 1) * 100 for k in ("record", "executed", "spy")]
    ctx.update(record=rec_r, executed=exe_r, spy=spy_r, lead=rec_r - spy_r)
    tiles = [("Paper record", _pct(rec_r), _cls(rec_r)), ("SPY", _pct(spy_r), ""), ("Lead on record", f"{rec_r - spy_r:+.2f} pts", _cls(rec_r - spy_r)),
             ("As executed", _pct(exe_r), _cls(exe_r)), ("Executed lead", f"{exe_r - spy_r:+.2f} pts", _cls(exe_r - spy_r))]
    parts.append('<div class="tiles">' + "".join(f'<div class="tile"><span>{a}</span><b class="{c}">{b}</b></div>' for a, b, c in tiles) + "</div>")
    md += [f"Paper record {rec_r:+.2f}% vs SPY {spy_r:+.2f}% ({rec_r - spy_r:+.2f} pts); as executed {exe_r:+.2f}% ({exe_r - spy_r:+.2f} pts)."]
    parts.append(f'<img alt="Paper account vs SPY" src="data:image/png;base64,{chart_paper(ps)}">')
    rr, sr = rets(ps["record"], start), rets(ps["spy"], start)
    rr, sr = rr.align(sr, join="inner")
    act = rr - sr
    parts.append(f'<h2>Daily lead over SPY</h2><img alt="Daily lead" src="data:image/png;base64,{chart_active(act)}">')
    rows = []
    for d in ps.index[::-1][:10]:
        i = ps.index.get_loc(d)
        rows.append([d.date().isoformat(), f"{(ps['record'].iloc[i] / start - 1) * 100:+.2f}%", f"{(ps['executed'].iloc[i] / start - 1) * 100:+.2f}%",
                     f"{(ps['spy'].iloc[i] / start - 1) * 100:+.2f}%", f"{(ps['record'].iloc[i] - ps['spy'].iloc[i]) / start * 100:+.2f}",
                     f"{(act.get(d, np.nan)) * 100:+.2f}" if d in act.index else "-"])
    parts.append("<h2>Last 10 days</h2>" + _table(["Date", "Record", "Executed", "SPY", "Lead (pts)", "Day's lead (pts)"], rows))

    if not real.empty:
        parts.append(f'<h2>Real money (Robinhood, both accounts combined) vs SPY from entry</h2><img alt="Real accounts vs SPY" src="data:image/png;base64,{chart_real(real)}">')
        ret = (real["value"].iloc[-1] / real.attrs["cost"] - 1) * 100
        sp = (real["spy"].iloc[-1] / real.attrs["cost"] - 1) * 100
        ctx.update(real_return=ret, real_spy=sp)
        parts.append(_table(["Account", "Through", "Value", "Return", "SPY same dollars", "Lead (pts)"],
                            [["Robinhood combined", real.index[-1].date().isoformat(), f"${real['value'].iloc[-1]:,.0f}",
                              f"{ret:+.2f}%", f"{sp:+.2f}%", f"{ret - sp:+.2f}"]]))
        md.append(f"Robinhood (combined): {ret:+.2f}% vs SPY {sp:+.2f}% ({ret - sp:+.2f} pts) through {real.index[-1].date()}.")
        parts.append("<p class='note'>Share counts in the real accounts are assumed from the lists given and have not been confirmed.</p>")

    ret_acc = combined_real(*[real_series(k) for k in sorted(_books()) if k.startswith("retire_")])
    if not ret_acc.empty:
        parts.append(f'<h2>Retirement accounts (combined) vs SPY from entry</h2><img alt="Retirement accounts vs SPY" src="data:image/png;base64,{chart_real(ret_acc)}">')
        ret = (ret_acc["value"].iloc[-1] / ret_acc.attrs["cost"] - 1) * 100
        sp = (ret_acc["spy"].iloc[-1] / ret_acc.attrs["cost"] - 1) * 100
        ctx.update(retire_return=ret, retire_spy=sp)
        parts.append(_table(["Account", "Through", "Value", "Return", "SPY same dollars", "Lead (pts)"],
                            [["Retirement combined", ret_acc.index[-1].date().isoformat(), f"${ret_acc['value'].iloc[-1]:,.0f}",
                              f"{ret:+.2f}%", f"{sp:+.2f}%", f"{ret - sp:+.2f}"]]))
        md.append(f"Retirement (combined): {ret:+.2f}% vs SPY {sp:+.2f}% ({ret - sp:+.2f} pts) through {ret_acc.index[-1].date()}.")

    rows = []
    for name in ("standard", "council"):
        d = _csv(f"daily_nav_shadow_{name}.csv")
        if not d.empty:
            r = d.iloc[-1]
            rows.append([{"standard": "Standard dossier", "council": "Council dossier"}[name], str(r["date"]),
                         f"${r['value']:,.0f}", f"{r['return_pct']:+.2f}%", f"{r['spy_return_pct']:+.2f}%",
                         f"{r['vs_spy_pct_pts']:+.2f}"])
    if rows:
        parts.append("<h2>Council test (hypothetical, never traded)</h2>" + _table(
            ["Portfolio", "Through", "Value", "Return", "SPY", "Lead (pts)"], rows))
        parts.append("<p class='note'>Both start at $10,000 at the first trade-date open after the council test began and "
                     "follow the PM's sandbox portfolio from the standard or the council verdicts each rebuild.</p>")
        md.append("Council test: " + "; ".join(f"{r[0]} {r[3]} ({r[5]} pts vs SPY)" for r in rows) + ".")

    if weekly:
        st = paper_stats(ps, loader)
        ctx["stats"] = st
        parts.append("<h1 class='break' style='margin-top:36px'>Statistics</h1>")
        parts.append(f"<div class='verdict'><b>{verdict(st)}</b></div>")
        md.append(verdict(st))
        a, b = st.get("active", {}), st.get("bootstrap", {})
        if st.get("n_days", 0) >= 3:
            cap = st.get("capm", {})
            srows = [["Trading days in the record", f"{st['n_days']}", "Everything below rests on this many days"],
                     ["Average daily lead", f"{a['mean'] * 100:+.3f}%", "Record minus SPY, per day"],
                     ["Tracking error (daily)", f"{a['te'] * 100:.2f}%", "How much the lead moves around"],
                     ["Information ratio (annualised)", f"{a['ir']:.1f}", "Lead per unit of risk; over a year or more, 0.5 is good"],
                     ["t-stat of daily lead", f"{a['t']:.2f}", "Needs about 2 to rule out luck"],
                     ["Bootstrap range of the lead (95%)", f"{b['lo'] * 100:+.1f} to {b['hi'] * 100:+.1f} pts", f"Block bootstrap, 3-day runs; observed {b['observed'] * 100:+.1f}"],
                     ["Chance noise alone gives this lead", f"{b['p_noise']:.0%}", "Bootstrap with the average lead set to zero"]]
            if cap.get("ok"):
                srows += [["Beta to SPY", f"{cap['beta']:.2f}", f"t = {cap['t']['market']:.1f}; above 1 means it moves more than the market"],
                          ["Alpha after beta (annualised)", f"{cap['alpha_annual'] * 100:+.1f}%", f"t = {cap['t']['alpha']:.2f}; short samples make this very noisy"]]
            srows += [["Max drawdown: record vs SPY", f"{st['dd_record'] * 100:.1f}% vs {st['dd_spy'] * 100:.1f}%", "Worst peak-to-trough so far"]]
            sp = st.get("sprt", {})
            srows += [["Sequential test (edge of 0.04%/day)", sp.get("decision", "n/a"), f"log-likelihood {sp.get('llr', 0):+.2f}; bounds {sp.get('lower', 0):.2f} / {sp.get('upper', 0):.2f}"]]
            parts.append("<h2>Is the lead more than noise?</h2>" + _table(["Measure", "Value", "What it means"], srows, text_last=True))
        fr = st.get("factors")
        if fr and fr.get("ok"):
            frs = [[k, f"{v:+.3f}", f"{fr['t'][k]:.1f}"] for k, v in fr["coef"].items() if k != "alpha"]
            parts.append("<h2>What the returns are exposed to</h2>" + _table(["Factor (ETF proxy)", "Loading", "t-stat"], frs)
                         + f"<p class='note'>Size = IWM-SPY, value = IVE-IVW, momentum = MTUM-SPY. R-squared {fr['r2']:.2f}; alpha {fr['alpha_annual'] * 100:+.1f}% a year.</p>")
        elif st.get("n_days", 0) < MIN_FACTOR_DAYS:
            parts.append(f"<h2>What the returns are exposed to</h2><p class='note'>Factor regression starts at {MIN_FACTOR_DAYS} trading days "
                         f"(have {st.get('n_days', 0)}): fewer days give loadings that are mostly noise.</p>")
        elif st.get("factors_error"):
            parts.append(f"<p class='note'>Factor regression unavailable: {st['factors_error']}</p>")

        rand = random_tests(loader, now=now, n=n_sims) if loader else []
        ctx["random"] = rand
        parts.append("<h2>Do we beat random picks? Three tests</h2>")
        png = chart_random(rand)
        if png:
            parts.append(f'<img alt="Picks vs random portfolios" src="data:image/png;base64,{png}">')
            trs = [[r["rebuild"], r["pool"], f"{r['days']}", f"{r['n_picks']}", f"{r['actual'] * 100:+.2f}%",
                    f"{r['random_mean'] * 100:+.2f}%", f"{r['beat_share']:.0%}"] for r in rand if r.get("ok")]
            parts.append(_table(["Rebuild", "Random pool", "Days", "Picks", "Ours", "Random avg", "Beats"], trs))
            parts.append(f"<p class='note'>{n_sims:,} random portfolios per row, same number of names and weights as the real picks. "
                         f"A rebuild with only a few days says little; read the rows with the most days. Test 1: are we better than chance? "
                         f"Test 2: do our picks beat random picks from our own shortlist (what the AI team and portfolio manager add)? "
                         f"Test 3: does the shortlist beat random stocks (what the quant screen adds)?</p>")
            for r in rand:
                if r.get("ok"):
                    md.append(f"Rebuild {r['rebuild']} ({r['days']}d, {r['pool']}): picks {r['actual'] * 100:+.2f}%, beat {r['beat_share']:.0%} of random portfolios.")
        else:
            parts.append("<p class='note'>Unavailable this run (no prices for the pools).</p>")

        hist = read_json(state_path("rebuild_history.json"), []) or []
        nav_hist = _csv("nav_history.csv")
        acl = None
        if not nav_hist.empty and "AI actual (after AI costs)" in nav_hist and "SPY" in nav_hist:
            lastrow = nav_hist.iloc[-1]
            acl = (lastrow["AI actual (after AI costs)"] / nav_hist["SPY"].iloc[0] - lastrow["SPY"] / nav_hist["SPY"].iloc[0]) * 100
        try:
            from . import freeze
            frozen = not freeze.diff(freeze.load_baseline() or {}, freeze.snapshot())
        except Exception:
            frozen = False
        rules, passed = checklist(st, rand, len({h["date"] for h in hist}), missing_days(ps.index), frozen, acl)
        ctx["checklist"] = rules
        parts.append(f"<h2>Go-live readiness: {passed} of {len(rules)} rules met</h2>")
        parts.append(_table(["Rule", "Now", "Met"], [[r, v, "<span class='good'>yes</span>" if ok else "<span class='bad'>no</span>"] for r, v, ok in rules]))
        parts.append("<p class='note'>The thresholds are a proposal (in <code>GO_LIVE</code> in pipeline/report.py and GO_LIVE.md); change them there. "
                     "This is a checklist for a human decision, not an instruction to trade.</p>")
        md.append(f"Go-live checklist: {passed} of {len(rules)} rules met.")
    parts.append("<p class='note'>Daily NAV rows use Yahoo closes (Alpaca fills a close Yahoo lacks). Past results do not predict future ones.</p>")
    return _wrap("".join(parts)), "\n".join(md), ctx


def _wrap(body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Portfolio performance</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def yahoo_closes(tickers, start):
    """Closes (auto-adjusted) for many tickers; start None = about 6 months. Chunked, tolerant of failures."""
    import yfinance as yf
    frames = []
    tick = sorted(set(tickers))
    for i in range(0, len(tick), 300):
        chunk = tick[i:i + 300]
        kw = {"start": str(pd.Timestamp(start).date())} if start is not None else {"period": "6mo"}
        try:
            d = yf.download([t.replace(".", "-") for t in chunk], progress=False, auto_adjust=True, threads=True, **kw)["Close"]
        except Exception:
            continue
        if isinstance(d, pd.Series):
            d = d.to_frame(chunk[0])
        d.columns = [str(c).replace("-", ".") for c in d.columns]
        frames.append(d)
    return pd.concat(frames, axis=1) if frames else pd.DataFrame()


def to_pdf(html_path, pdf_path):
    """Print the saved HTML report to PDF with headless Chromium (Playwright). Returns True on success."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(Path(html_path).resolve().as_uri())
            pg.pdf(path=str(pdf_path), format="Letter", print_background=True,
                   margin={"top": "14mm", "bottom": "14mm", "left": "13mm", "right": "13mm"})
            b.close()
        return True
    except Exception as e:
        print(f"! PDF not made ({str(e)[:100]})")
        return False


def main(argv):
    weekly = "--weekly" in argv
    html, md, ctx = build(weekly=weekly, loader=yahoo_closes if weekly else None)
    root = private_reports("performance")              # shows real holdings: private repo only
    stamp = ctx["date"] + ("-weekly" if weekly else "")
    for name in (f"{stamp}.html", "latest.html" if not weekly else "latest-weekly.html"):
        (root / name).write_text(html)
    (root / ("latest.md" if not weekly else "latest-weekly.md")).write_text(md)
    if "--pdf" in argv:
        to_pdf(root / f"{stamp}.html", root / ("latest.pdf" if not weekly else "latest-weekly.pdf"))
    print(f"Saved to the private repo: reports/performance/ (not printed: this log is public)")
    if "--email" in argv:
        from .notify import send
        try:
            how = send(f"Portfolio {'statistics' if weekly else 'performance'} report - {ctx['date']}", md, html=html,
                       attachments=[root / f"{stamp}.html"], save_dir=root)
            print(f"email: {how}")
        except Exception as e:
            print(f"! report email failed ({str(e)[:100]}); the report is saved in {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
