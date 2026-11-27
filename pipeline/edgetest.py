"""
EDGE TESTS  —  three ideas tested on history; runs with the screen backtest (python -m pipeline.screentest).
Analysis only: nothing live changes.

  1. Holding period   Does the current screen (and each main signal alone) work better held 1, 3 or 6 months?
                      Top-2-per-sector portfolios, rebuilt only as often as they are held, so periods never
                      overlap; with the yearly trading cost each pace implies.
  2. Read-across      When same-sub-industry peers report earnings before a company does, does the peers'
                      average reaction say anything about that company's next weeks?
  3. Insider buying   After open-market purchases by officers and directors (SEC Forms 4, the SEC's quarterly
                      Insider Transactions Data Sets), and especially clusters of several insiders buying within
                      90 days, what did the stock do over the next 1, 3 and 6 months?

All returns are against the stock's sector (equal-weighted among the sampled stocks that day) with single moves
capped. Longer holds use every third or sixth month-end with each possible starting month averaged, so their
t-stats are not inflated by overlapping windows. Outputs: reports/screentest/edges.md, state/edgetest.json.
"""
import bisect
import io
import zipfile

import numpy as np
import pandas as pd

from . import history
from . import screentest as st
from .util import now_et

HORIZONS = ((20, 1, "1 month"), (60, 3, "3 months"), (120, 6, "6 months"))     # trading days, months between rebuilds
PEER_DAYS, SETTLE_DAYS = 35, 4          # peers' reports this recent count; a report needs this long to show its reaction
INSIDER_DAYS = 90
INSIDER_URLS = ("https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
                "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{q}_form345.zip")


# ==================================================================== shared
def add_horizons(df, px):
    """fwd<H> and resid<H> (vs the day's equal-weighted sector, capped) for each horizon."""
    df = df.copy()
    pos = {ts.date().isoformat(): i for i, ts in enumerate(px.index)}
    for H, _, _ in HORIZONS:
        cap = st.RETURN_CAP * np.sqrt(H / 20)
        f = {}
        for d in df["date"].unique():
            i = pos[d]
            if i + 1 + H < len(px):
                f[d] = px.iloc[i + 1 + H] / px.iloc[i + 1] - 1
        v = pd.Series([f[d].get(t, np.nan) if d in f else np.nan for d, t in zip(df["date"], df["ticker"])], index=df.index)
        df[f"fwd{H}"] = v.clip(-cap, cap)
        df[f"resid{H}"] = df[f"fwd{H}"] - df.groupby(["date", "sector"])[f"fwd{H}"].transform("mean")
    return df


def _avg(stats):
    """Average the per-starting-month results: mean of the yearly means and of the t-stats."""
    ok = [s for s in stats if s["t"] is not None]
    if not ok:
        return {"mean": None, "t": None, "periods": 0}
    return {"mean": round(float(np.mean([s["mean"] for s in ok])), 4), "t": round(float(np.mean([s["t"] for s in ok])), 2),
            "periods": int(np.mean([s["n"] for s in ok]))}


def _series_stat(s, per_year):
    s = pd.Series(s).dropna()
    if len(s) < 8:
        return {"mean": None, "t": None, "n": len(s)}
    se = s.std(ddof=1) / np.sqrt(len(s))
    return {"mean": float(s.mean() * per_year), "t": float(s.mean() / se) if se > 0 else None, "n": len(s)}


# ==================================================================== 1. holding period
def horizon_test(df, current_w, start):
    """{mix: {horizon label: {ic, excess a year, after costs, turnover}}} on the out-of-sample months."""
    df, names = st.add_scores(df)
    cur = {k: v for k, v in current_w.items() if k in names and v > 0}
    mixes = {"Current screen": cur}
    for label, k in (("Value alone", "value"), ("Quality alone", "quality"), ("12-month momentum alone", "momentum"),
                     ("Earnings reaction alone", "reaction"), ("1-month reversal alone", "reversal"),
                     ("Low short interest alone", "low_short")):
        if k in names:
            mixes[label] = {k: 1.0}
    months = sorted(m for m in df["date"].unique() if m >= start)
    out = {}
    for label, w in mixes.items():
        d = df.assign(c=st.composite(df, w))
        out[label] = {}
        for H, step, hl in HORIZONS:
            ex_stats, ic_stats, turns = [], [], []
            for o in range(step):
                ex, ic, prev = [], [], None
                for date in months[o::step]:
                    g = d[(d["date"] == date) & d[f"fwd{H}"].notna()]
                    if len(g) < 50:
                        continue
                    r = g[f"resid{H}"].groupby(g["sector"]).rank(pct=True)
                    cs = [x["c"].corr(r.loc[x.index]) for _, x in g.groupby("sector") if len(x) >= 5 and x["c"].nunique() > 1]
                    cs = [v for v in cs if v == v]
                    top = g.sort_values("c", ascending=False).groupby("sector").head(st.TOP_PER_SECTOR)
                    ex.append(top[f"fwd{H}"].mean() - g[f"fwd{H}"].mean())
                    ic.append(np.mean(cs) if cs else np.nan)
                    held = set(top["ticker"])
                    if prev:
                        turns.append(1 - len(held & prev) / len(held))
                    prev = held
                ex_stats.append(_series_stat(ex, 12 / step))
                ic_stats.append(_series_stat(ic, 1))
            e, i = _avg(ex_stats), _avg(ic_stats)
            turn = float(np.mean(turns)) if turns else None
            cost = None if turn is None else turn * 2 * st.COST_PER_TRADE * 12 / step
            out[label][hl] = {"ic": i["mean"], "ic_t": i["t"], "excess": e["mean"], "t": e["t"], "periods": e["periods"],
                              "turnover": None if turn is None else round(turn, 3),
                              "after_costs": None if e["mean"] is None or cost is None else round(e["mean"] - cost, 4)}
    return out


# ==================================================================== 2. read-across
def read_across_raw(df, reactions, sub_of):
    """Per sample, the average earnings reaction of same-sub-industry peers that reported in the last PEER_DAYS
    (and at least SETTLE_DAYS ago, so the reaction is known) and after the stock's own last report."""
    rdates = {t: [str(d)[:10] for d, _ in rows] for t, rows in reactions.items() if rows}
    rvals = {t: [r for _, r in rows] for t, rows in reactions.items() if rows}
    out = pd.Series(np.nan, index=df.index)
    for date, g in df.groupby("date"):
        d0 = pd.Timestamp(date)
        hi, lo = (d0 - pd.Timedelta(days=SETTLE_DAYS)).date().isoformat(), (d0 - pd.Timedelta(days=PEER_DAYS)).date().isoformat()
        last = {}
        for t in g["ticker"]:
            ds = rdates.get(t)
            if ds:
                k = bisect.bisect_right(ds, hi) - 1
                if k >= 0:
                    last[t] = (ds[k], rvals[t][k])
        groups = {}
        for t in g["ticker"]:
            groups.setdefault((sub_of or {}).get(t) or "?", []).append(t)
        val = {}
        for sub, ts in groups.items():
            if sub == "?":
                continue
            recent = [(last[p][0], p, last[p][1]) for p in ts if p in last and last[p][0] > lo]
            for t in ts:
                own = last.get(t, ("", 0))[0]
                peers = [v for d, p, v in recent if p != t and d > own]
                if peers:
                    val[t] = float(np.mean(peers))
        out.loc[g.index] = g["ticker"].map(val).to_numpy()
    return out


def read_across_test(df, reactions, sub_of):
    df = df.assign(ra=read_across_raw(df, reactions, sub_of))
    have = df[df["ra"].notna()]
    months = sorted(df["date"].unique())
    mid = months[len(months) // 2]
    out = {"coverage": round(float(df["ra"].notna().mean()), 3), "split_at": mid, "horizons": {}}
    for H, step, hl in HORIZONS[:2]:
        ics, spreads = {}, {}
        for date, g in have[have[f"resid{H}"].notna()].groupby("date"):
            if len(g) < 30:
                continue
            ics[date] = g["ra"].rank().corr(g[f"resid{H}"].rank())
            q = g["ra"].rank(pct=True)
            spreads[date] = g.loc[q > 2 / 3, f"resid{H}"].mean() - g.loc[q <= 1 / 3, f"resid{H}"].mean()
        res = {}
        for name, s in (("ic", ics), ("spread", spreads)):
            per = [_series_stat([v for d, v in sorted(s.items())][o::step], 12 / step if name == "spread" else 1) for o in range(step)]
            a = _avg(per)
            h1 = _avg([_series_stat([v for d, v in sorted(s.items()) if d < mid][o::step], 1) for o in range(step)])
            h2 = _avg([_series_stat([v for d, v in sorted(s.items()) if d >= mid][o::step], 1) for o in range(step)])
            res[name] = {"mean": a["mean"], "t": a["t"], "first_half_t": h1["t"], "second_half_t": h2["t"]}
        out["horizons"][hl] = res
    return out


# ==================================================================== 3. insider buying
def _col(cols, *needles):
    for c in cols:
        u = c.upper().replace("_", "")
        if all(n in u for n in needles):
            return c
    raise KeyError(f"no column with {needles} in {list(cols)[:30]}")


def parse_insider_zip(raw, ciks):
    """Open-market purchases by officers and directors of the given issuers from one quarterly SEC data set."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = {n.upper().split("/")[-1]: n for n in z.namelist()}
    rd = lambda n: pd.read_csv(z.open(names[n]), sep="\t", dtype=str, low_memory=False)
    sub, own, tr = rd("SUBMISSION.TSV"), rd("REPORTINGOWNER.TSV"), rd("NONDERIV_TRANS.TSV")
    acc = _col(tr.columns, "ACCESSION")
    code, ad = _col(tr.columns, "TRANSCODE"), _col(tr.columns, "ACQUIREDDISP")
    sh, pr = _col(tr.columns, "TRANSSHARES"), _col(tr.columns, "PRICEPERSHARE")
    tr = tr[(tr[code] == "P") & (tr[ad] == "A")]
    tr = tr.assign(value=pd.to_numeric(tr[sh], errors="coerce") * pd.to_numeric(tr[pr], errors="coerce"))
    tr = tr[tr["value"] > 0].groupby(acc, as_index=False)["value"].sum()
    s_acc, cik, filed = _col(sub.columns, "ACCESSION"), _col(sub.columns, "ISSUERCIK"), _col(sub.columns, "FILINGDATE")
    sub = sub[[s_acc, cik, filed]].rename(columns={s_acc: "acc", cik: "cik", filed: "filed"})
    sub["cik"] = pd.to_numeric(sub["cik"], errors="coerce")
    sub = sub[sub["cik"].isin(ciks)]
    o_acc, ocik, rel = _col(own.columns, "ACCESSION"), _col(own.columns, "OWNERCIK"), _col(own.columns, "RELATIONSHIP")
    own = own[[o_acc, ocik, rel]].rename(columns={o_acc: "acc", ocik: "owner", rel: "rel"})
    own = own[own["rel"].fillna("").str.contains("Officer|Director", case=False)].drop_duplicates("acc")
    m = tr.rename(columns={acc: "acc"}).merge(sub, on="acc").merge(own, on="acc")
    m["filed"] = pd.to_datetime(m["filed"], errors="coerce", format="mixed").dt.date.astype(str)
    return m[["cik", "filed", "owner", "value"]]


def insider_history(ciks, headers, start="2009q3", get=None):
    """Every quarter's purchases from `start` on, cached in cache/insider_buys.pkl (quarters already read are kept)."""
    import requests
    get = get or requests.get
    c = history._cache("insider_buys.pkl", {"quarters": {}})
    today = now_et().date()
    y, q = int(start[:4]), int(start[5])
    wanted = []
    while (y, q) <= (today.year, (today.month - 1) // 3 + 1):
        wanted.append(f"{y}q{q}")
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    new = 0
    for name in wanted[:-1]:                           # the current quarter is not published until it ends
        if name in c["quarters"]:
            continue
        raw = None
        for url in INSIDER_URLS:
            try:
                r = get(url.format(q=name), headers=headers, timeout=120)
                if r.status_code == 200 and r.content[:2] == b"PK":
                    raw = r.content
                    break
            except Exception as e:
                print(f"    ! {name}: {str(e)[:80]}")
        if raw is None:
            print(f"    ! insider data {name}: not available")
            continue
        try:
            c["quarters"][name] = parse_insider_zip(raw, ciks)
            new += 1
        except Exception as e:
            print(f"    ! insider data {name}: {type(e).__name__} {str(e)[:150]}")
        if new and new % 10 == 0:
            history._save("insider_buys.pkl", c)
    if new:
        history._save("insider_buys.pkl", c)
    frames = [f for f in c["quarters"].values() if len(f)]
    print(f"    insider purchases: {len(c['quarters'])} quarters ({new} new), {sum(len(f) for f in frames):,} filings")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["cik", "filed", "owner", "value"])


def insider_flags(df, buys, cik_of):
    """Per sample: distinct insider buyers and dollars bought in the INSIDER_DAYS before the sample date."""
    df = df.assign(cik=df["ticker"].map(cik_of))
    b = buys.dropna(subset=["cik"]).sort_values("filed")
    n, val = pd.Series(0, index=df.index), pd.Series(0.0, index=df.index)
    for date, g in df.groupby("date"):
        lo = (pd.Timestamp(date) - pd.Timedelta(days=INSIDER_DAYS)).date().isoformat()
        w = b[(b["filed"] > lo) & (b["filed"] <= date)]
        if not len(w):
            continue
        agg = w.groupby("cik").agg(n=("owner", "nunique"), value=("value", "sum"))
        n.loc[g.index] = g["cik"].map(agg["n"]).fillna(0).astype(int).to_numpy()
        val.loc[g.index] = g["cik"].map(agg["value"]).fillna(0.0).to_numpy()
    return n, val


def insider_test(df, buys, cik_of):
    n, val = insider_flags(df, buys, cik_of)
    months = sorted(df["date"].unique())
    mid = months[len(months) // 2]
    flags = {"Any officer or director bought (last 90 days)": n >= 1, "Cluster: 2 or more insiders bought": n >= 2,
             "Cluster: 3 or more insiders bought": n >= 3, "Insiders bought $500,000 or more in total": val >= 5e5}
    out = {"split_at": mid, "filings": int(len(buys)), "flags": {}}
    for label, f in flags.items():
        res = {"share": round(float(f.mean()), 4)}
        for H, step, hl in HORIZONS:
            sel = df.loc[f & df[f"resid{H}"].notna()]
            grp = sel.groupby("date")[f"resid{H}"]
            by = grp.mean()[grp.size() >= 3]
            a = _avg([_series_stat(by.sort_index().iloc[o::step], 12 / step) for o in range(step)])
            h1 = _avg([_series_stat(by[by.index < mid].sort_index().iloc[o::step], 12 / step) for o in range(step)])
            h2 = _avg([_series_stat(by[by.index >= mid].sort_index().iloc[o::step], 12 / step) for o in range(step)])
            res[hl] = {"mean": a["mean"], "t": a["t"], "first_half_t": h1["t"], "second_half_t": h2["t"]}
        out["flags"][label] = res
    return out


# ==================================================================== run and report
def run(df, px, current_w, start, reactions, sub_of, buys=None, cik_of=None):
    df = add_horizons(df, px)
    if "resid" not in df:
        df["resid"] = df["resid20"]
    res = {"built": now_et().date().isoformat(), "first_test_month": start,
           "horizons": horizon_test(df, current_w, start), "read_across": read_across_test(df, reactions, sub_of)}
    if buys is not None and len(buys):
        res["insider"] = insider_test(df, buys, cik_of or {})
    return res


def report(res):
    pct = st.pct
    f2 = lambda x: "n/a" if x is None else f"{x:+.2f}"
    L = [f"# Edge tests ({res['built']})", "",
         "Three ideas tested on the same history as the screen backtest. Returns are against the stock's sector, single "
         "moves capped. Holds longer than a month are rebuilt only as often as they are held, so periods never overlap.", "",
         f"## 1. Holding period (out of sample from {res['first_test_month']})", "",
         "Top-2-per-sector portfolio against the equal-weighted universe, a year, before and after trading costs "
         f"({st.COST_PER_TRADE * 1e4:.0f} basis points each way).", "",
         "| Mix | Hold | Excess a year | t | After costs | Names replaced each rebuild | IC | IC t |", "|---|---|---|---|---|---|---|---|"]
    for mix, hs in res["horizons"].items():
        for hl, v in hs.items():
            L.append(f"| {mix} | {hl} | {pct(v['excess'])} | {f2(v['t'])} | {pct(v['after_costs'])} | "
                     f"{'n/a' if v['turnover'] is None else f'{v['turnover'] * 100:.0f}%'} | "
                     f"{'n/a' if v['ic'] is None else f'{v['ic']:+.4f}'} | {f2(v['ic_t'])} |")
    ra = res["read_across"]
    L += ["", "## 2. Read-across from peers' earnings", "",
          f"Signal: the average earnings-day reaction of same-sub-industry peers that reported in the last {PEER_DAYS} days and "
          f"after the stock's own last report. Available for {ra['coverage'] * 100:.0f}% of stock-months. 'Spread' is the top "
          f"third minus the bottom third of covered stocks, a year.", "",
          "| Horizon | IC | t | First half t | Second half t | Spread a year | t | First half t | Second half t |", "|---|---|---|---|---|---|---|---|---|"]
    for hl, v in ra["horizons"].items():
        L.append(f"| {hl} | {'n/a' if v['ic']['mean'] is None else f'{v['ic']['mean']:+.4f}'} | {f2(v['ic']['t'])} | {f2(v['ic']['first_half_t'])} | "
                 f"{f2(v['ic']['second_half_t'])} | {pct(v['spread']['mean'])} | {f2(v['spread']['t'])} | {f2(v['spread']['first_half_t'])} | "
                 f"{f2(v['spread']['second_half_t'])} |")
    ins = res.get("insider")
    if ins:
        L += ["", "## 3. Insider buying", "",
              f"Open-market purchases by officers and directors filed in the {INSIDER_DAYS} days before each month-end "
              f"({ins['filings']:,} filings for today's index members). What the flagged stocks earned against their sector "
              f"afterwards, a year, with t-stats for all years and each half (split at {ins['split_at']}).", "",
              "| Flag | Share of stock-months | Next 1 month | t (halves) | Next 3 months | t (halves) | Next 6 months | t (halves) |",
              "|---|---|---|---|---|---|---|---|"]
        for label, v in ins["flags"].items():
            cells = [f"{pct(v[hl]['mean'])} | {f2(v[hl]['t'])} ({f2(v[hl]['first_half_t'])}, {f2(v[hl]['second_half_t'])})"
                     for _, _, hl in HORIZONS]
            L.append(f"| {label} | {v['share'] * 100:.1f}% | " + " | ".join(cells) + " |")
    else:
        L += ["", "## 3. Insider buying", "", "Not run: the SEC insider data could not be loaded in this run."]
    L += ["", "## Limits", "",
          "- Today's index members only, so companies that failed are missing; this flatters buying beaten-down or "
          "insider-bought stocks in particular.",
          "- Insider data uses the filing date, so nothing is known before it was public. Purchases by 10% owners who are "
          "not officers or directors are left out.",
          "- With several mixes, horizons and flags tried, treat a t under about 3 as suggestive only."]
    return "\n".join(L) + "\n"
