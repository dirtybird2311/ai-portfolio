"""
SHADOW BOOKS  —  hypothetical portfolios tracked beside the real one, never traded.

Each book is a list of segments: on a segment's start date the book is rebuilt at that day's opening prices to the
segment's target weights (whatever is left over sits in cash), then held until the next segment. Every book starts at
$10,000 on its first segment's open and is compared with the same dollars put into SPY at that open.

Used for the council test: "standard" holds the portfolio the PM builds from the standard judges, "council" the one
it builds when the council judge stands in for the live Sonnet judge (pipeline/council_plan.py adds both each rebuild).
The daily rows go to state/daily_nav_shadow_<name>.csv; the nightly NAV backfill refreshes them.
"""
import pandas as pd

from .util import read_json, state_path, write_json

FILE = "shadow_books.json"
START_VALUE = 10000.0


def load():
    return read_json(state_path(FILE), {}) or {"books": {}}


def add_segment(name, start, weights, label=None, note=None):
    """Set book `name` to `weights` (percent of the book) from the open of `start` (YYYY-MM-DD). Re-adding the same
    start replaces that segment, so a rerun never stacks duplicates."""
    d = load()
    b = d["books"].setdefault(name, {"label": label or name, "segments": []})
    if label:
        b["label"] = label
    b["segments"] = [s for s in b["segments"] if s["start"] != start] + [
        {"start": start, "weights": {t: float(w) for t, w in weights.items() if w}, **({"note": note} if note else {})}]
    b["segments"].sort(key=lambda s: s["start"])
    write_json(state_path(FILE), d)
    return b


def series(book, close, open_, start_value=START_VALUE):
    """Daily closing value of one book and of the same dollars in SPY: DataFrame(value, spy)."""
    segs = book["segments"]
    if not segs:
        return pd.DataFrame(columns=["value", "spy"])
    first = pd.Timestamp(segs[0]["start"])
    days = [d for d in close.index if d >= first]
    spy_in = float(open_["SPY"].loc[first])
    value, rows, k = start_value, [], -1
    shares, cash = {}, 0.0
    for d in days:
        while k + 1 < len(segs) and pd.Timestamp(segs[k + 1]["start"]) <= d:
            k += 1
            s = pd.Timestamp(segs[k]["start"])
            if k > 0:                          # rebalance at this open: the old holdings' value at the open
                value = cash + sum(n * float(open_[t].loc[s]) for t, n in shares.items())
            w = segs[k]["weights"]
            shares = {t: value * pct / 100 / float(open_[t].loc[s]) for t, pct in w.items()}
            cash = value * (1 - sum(w.values()) / 100)
        px = {t: close[t].loc[:d].dropna() for t in shares}
        if any(p.empty for p in px.values()):
            continue
        v = cash + sum(n * float(px[t].iloc[-1]) for t, n in shares.items())
        rows.append({"date": d, "value": v, "spy": start_value * float(close["SPY"].loc[d]) / spy_in})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["value", "spy"])


def tickers():
    return sorted({t for b in load()["books"].values() for s in b["segments"] for t in s["weights"]} | {"SPY"})


def write_all(close, open_):
    """Refresh state/daily_nav_shadow_<name>.csv for every book. Returns {name: last row} for printing."""
    out = {}
    for name, b in load()["books"].items():
        try:
            s = series(b, close, open_)
        except KeyError as e:                  # a price missing for a segment's start day: try again tomorrow
            print(f"    shadow book {name}: no price for {e}; skipped")
            continue
        if s.empty:
            continue
        df = pd.DataFrame({"date": [d.date().isoformat() for d in s.index], "value": s["value"].round(2),
                           "return_pct": ((s["value"] / START_VALUE - 1) * 100).round(2),
                           "spy_return_pct": ((s["spy"] / START_VALUE - 1) * 100).round(2)})
        df["vs_spy_pct_pts"] = (df["return_pct"] - df["spy_return_pct"]).round(2)
        df.to_csv(state_path(f"daily_nav_shadow_{name}.csv"), index=False)
        out[name] = df.iloc[-1].to_dict()
    return out


def refresh():
    """Download opens and closes (Yahoo) and rewrite every shadow book's daily file."""
    d = load()
    if not d["books"]:
        return {}
    import yfinance as yf
    start = min(s["start"] for b in d["books"].values() for s in b["segments"])
    tk = tickers()
    raw = yf.download([t.replace(".", "-") for t in tk], start=start, progress=False, auto_adjust=False)
    close, open_ = raw["Close"], raw["Open"]
    for f in (close, open_):
        f.columns = [c.replace("-", ".") for c in f.columns]
    out = write_all(close, open_)
    for name, r in out.items():
        print(f"    shadow {name}: {r['return_pct']:+.2f}% vs SPY {r['spy_return_pct']:+.2f}% ({r['vs_spy_pct_pts']:+.2f} pts) "
              f"through {r['date']}")
    return out
