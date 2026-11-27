"""
BACKFILL the whole-account NAV (state/daily_account_nav.csv) for trading days that have no row.
run:  python -m pipeline.navfill            (Actions > Backfill account NAV)

Rebuilds what the paper account held at each day's close from state/trades.csv (shares and cash after
that day's trades) and prices it at Yahoo closing prices; SPY benchmark from the first day, as the daily
watch does. Rows that already exist are left alone unless --all.
"""
import argparse

import pandas as pd

from .book import STARTING_CASH
from .util import now_et, read_json, state_path, write_json
from . import prices
from .watch import ACCOUNT_NAV_FILE, EXTERNAL_FILE, as_record, inception, nav_snapshot, SKIPS


def holdings_by_day(trades, days):
    """{day: ({ticker: shares}, cash)} at each day's close."""
    t = trades.copy()
    t["day"] = t["date"].astype(str).str[:10]
    t["shares"] = t["shares"].astype(float)
    t["amount"] = t["amount"].astype(float)
    out = {}
    for d in days:
        done = t[t["day"] <= d]
        sh = {}
        for r in done.itertuples():
            sh[r.ticker] = sh.get(r.ticker, 0.0) + (r.shares if r.action == "BUY" else -r.shares)
        cash = sum(STARTING_CASH.values()) - done.loc[done.action == "BUY", "amount"].sum() \
            + done.loc[done.action == "SELL", "amount"].sum()
        out[d] = ({k: v for k, v in sh.items() if abs(v) > 1e-6}, float(cash))
    return out


ADJUST_FILE = "adjusted_book.json"   # "what the account would hold had a late rebuild traded when planned"


def moves_of(adj):
    """The late rebuilds to move: adj["moves"] (a list), or the single actual/planned pair of older files."""
    if adj.get("moves"):
        return [m for m in adj["moves"] if m.get("actual_date") and m.get("planned_date")]
    return [{"actual_date": adj["actual_date"], "planned_date": adj["planned_date"]}] if adj.get("actual_date") else []


def shadow_trades(trades, adj, opens):
    """The trade log with each late rebuild's trades (those dated a move's actual_date) moved to its planned_date
    at that day's opening prices: same shares sold, same dollars spent on each buy."""
    t = trades.copy()
    for c in ("shares", "amount", "price"):
        t[c] = t[c].astype(float)
    for mv in moves_of(adj):
        day = t["date"].astype(str).str[:10]
        m = day == mv["actual_date"]
        ts = pd.Timestamp(mv["planned_date"])
        for i in t.index[m]:
            px = float(opens[t.at[i, "ticker"]].loc[ts])
            if t.at[i, "action"] == "SELL":
                t.at[i, "amount"] = float(t.at[i, "shares"]) * px
            else:
                t.at[i, "shares"] = float(t.at[i, "amount"]) / px
            t.at[i, "price"], t.at[i, "date"] = px, mv["planned_date"]
    return close_full_exits(t, trades)


def close_full_exits(st, trades):
    """Moving a rebuild changes how many shares each buy got, so a later sale of "all of it" (sized from the real
    account) would leave a sliver behind, or sell more than the shadow book holds. Every sale that empties the real
    position empties the shadow one instead, and no sale sells more than the shadow book holds."""
    real, full = {}, set()
    for i in trades.index:
        r = trades.loc[i]
        n = float(r["shares"]) * (1 if r["action"] == "BUY" else -1)
        real[r["ticker"]] = real.get(r["ticker"], 0.0) + n
        if r["action"] == "SELL" and abs(real[r["ticker"]]) < 1e-6:
            full.add(i)
    st = st.copy()
    st["shares"], st["amount"] = st["shares"].astype(float), st["amount"].astype(float)
    held = {}
    order = sorted(st.index, key=lambda i: (str(st.at[i, "date"])[:10], list(st.index).index(i)))
    for i in order:
        tk = st.at[i, "ticker"]
        if st.at[i, "action"] == "BUY":
            held[tk] = held.get(tk, 0.0) + float(st.at[i, "shares"])
            continue
        have = max(held.get(tk, 0.0), 0.0)
        if i in full or float(st.at[i, "shares"]) > have:
            st.at[i, "shares"] = have
            st.at[i, "amount"] = have * float(st.at[i, "price"])
        held[tk] = have - float(st.at[i, "shares"])
    return st


def rows(close, trades, start, start_value, spy_in):
    spy = close["SPY"].dropna()
    days = [d.date().isoformat() for d in spy.index if d.date().isoformat() >= start]
    out = []
    for d, (sh, cash) in holdings_by_day(trades, days).items():
        ts = pd.Timestamp(d)
        px = {k: close[k].dropna().loc[:ts] for k in sh}
        if any(s.empty or s.index[-1] != ts for s in px.values()):
            print(f"    {d}: a holding has no close that day; skipped")
            continue
        value = cash + sum(n * float(px[k].iloc[-1]) for k, n in sh.items())
        spy_now = float(spy.loc[ts])
        out.append({"date": d, "since": start, "account_value": round(value, 2), "start_value": round(start_value, 2),
                    "return_pct": round((value / start_value - 1) * 100, 2),
                    "spy_return_pct": round((spy_now / spy_in - 1) * 100, 2),
                    "vs_spy_pct_pts": round((value / start_value - spy_now / spy_in) * 100, 2)})
    return out


GAP_JUMP = 5.0          # pts: the record (as planned) and executed books hold nearly the same stocks, so their gap
                        # can't swing this much in a day; a bigger swing is a data fault in one of them


def consistent(add, old):
    """Drop any new row whose record-vs-executed gap moved more than GAP_JUMP pts from the previous day's."""
    allr = {str(r["date"]): r for r in old.to_dict("records")} if len(old) else {}
    allr.update({r["date"]: r for r in add})
    ok, prev = [], None
    for d in sorted(allr):
        r = allr[d]
        gap = (float(r["record_return_pct"]) - float(r["executed_return_pct"])
               if pd.notna(r.get("record_return_pct")) and pd.notna(r.get("executed_return_pct")) else None)
        bad = gap is not None and prev is not None and abs(gap - prev) > GAP_JUMP
        if any(a is r for a in add):
            if bad:
                SKIPS.append(f"{d}: record vs executed gap moved {gap - prev:+.1f} pts in a day (a price fault); not saved")
                continue
            ok.append(r)
        if not bad and gap is not None:
            prev = gap
    return ok


def mine_cols(old, day):
    """Columns that hold a value in the saved row for this day."""
    row = old[old["date"].astype(str) == day]
    return set() if row.empty else {c for c in row.columns if pd.notna(row[c].iloc[0])}


def fill_external(close, all_rows=False):
    """Daily NAV rows for the real accounts (state/external_books.json) on days that have none: each book is
    priced at that day's closes against SPY from the entry price, exactly as the daily watch does."""
    ext = read_json(state_path(EXTERNAL_FILE), {}) or {}
    added = 0
    spy = close["SPY"].dropna()
    for name, b in (ext.get("books") or {}).items():
        nav_file = f"daily_nav_{name}.csv"
        path = state_path(nav_file)
        have = set(pd.read_csv(path)["date"].astype(str)) if path.exists() else set()
        phases = b.get("phases") or []             # what the account held before the current book, each "until" a date
        first = min(str(lot["date"])[:10] for p in b.get("positions", []) + [q for ph in phases for q in ph["positions"]]
                    for lot in (p.get("lots") or [{"date": p.get("buy_date")}]))
        for ts in spy.index:                       # active_from: the day the current positions took over (after a rebalance)
            d = ts.date().isoformat()
            start = first if phases else max(first, str(b.get("active_from", first))[:10])
            if d < start or (d in have and not all_rows):
                continue
            ph = next((x for x in phases if d <= str(x["until"])[:10]), None)
            snap = {"positions": ph["positions"], "cash": ph.get("cash")} if ph else b
            r = nav_snapshot(snap, close.loc[:ts], today=ts.date(), nav_file=nav_file)
            if r:
                added += 1
    if added:
        print(f"    real accounts: {added} daily rows added (details kept private)")
    return added


def main(all_rows=False):
    import yfinance as yf
    inc = inception()
    if not inc:
        print("No trades yet: nothing to backfill.")
        return {"status": "empty"}
    start, start_value, spy_in = inc
    trades = pd.read_csv(state_path("trades.csv"))
    ext = read_json(state_path(EXTERNAL_FILE), {}) or {}
    ext_tickers = {p["ticker"] for b in (ext.get("books") or {}).values()
                   for p in b.get("positions", []) + [q for ph in b.get("phases", []) for q in ph["positions"]]}
    tickers = sorted(set(trades["ticker"]) | {"SPY"} | ext_tickers)
    end = (now_et().date() + pd.Timedelta(days=1)).isoformat()
    d = yf.download([t.replace(".", "-") for t in tickers], start=start, end=end, progress=False, auto_adjust=False)
    close = d["Close"]
    close.columns = [c.replace("-", ".") for c in close.columns]
    lines, short = prices.fill_gaps(close, tickers)
    for ln in lines:
        print(f"    {ln}")
    if short:
        print(f"    ! no newest close yet for {', '.join(sorted(short))}; their latest day will be skipped")
    if spy_in is None:
        spy_in = float(close["SPY"].dropna().loc[:pd.Timestamp(start)].iloc[-1])
    new = rows(close, trades, start, start_value, spy_in)
    adj = read_json(state_path(ADJUST_FILE))
    if adj:
        st = shadow_trades(trades, adj, d["Open"].rename(columns=lambda c: c.replace("-", ".")))
        shadow = {r["date"]: r for r in rows(close, st, start, start_value, spy_in)}
        for r in new:
            a = shadow.get(r["date"])
            if a:
                r["adjusted_value"], r["adjusted_return_pct"] = a["account_value"], a["return_pct"]
                r["adjusted_vs_spy_pct_pts"] = a["vs_spy_pct_pts"]
        last_day = max(shadow) if shadow else None
        if last_day:                           # holdings the daily watch prices from here on
            sh, cash = holdings_by_day(st, [last_day])[last_day]
            adj.update(shares=sh, cash=round(cash, 2), as_of=last_day)
            write_json(state_path(ADJUST_FILE), adj)
    new = [as_record(r) for r in new]
    path = state_path(ACCOUNT_NAV_FILE)
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=list(new[0]) if new else [])
    have = set(old["date"].astype(str)) if len(old) else set()
    for r in new:
        tag = "kept" if r["date"] in have and not all_rows else "added"
        mine = old[old["date"].astype(str) == r["date"]]
        cmp = f" (saved row: {float(mine['record_value'].iloc[0]):,.2f})" if len(mine) and "record_value" in mine else ""
        print(f"    {r['date']}: ${r['record_value']:,.2f}  {r['record_return_pct']:+.2f}% vs SPY {r['spy_return_pct']:+.2f}%  "
              f"({r['record_basis']}) [{tag}]{cmp}")
    add = [r for r in new if all_rows or r["date"] not in have or "record_value" not in mine_cols(old, r["date"])]
    add = consistent(add, old)
    keep = old[~old["date"].astype(str).isin({r["date"] for r in add})] if len(old) else old
    pd.concat([keep, pd.DataFrame(add)]).sort_values("date").to_csv(path, index=False)
    n_ext = fill_external(close, all_rows)
    try:                                       # hypothetical books (council test): never block the real rows
        from . import shadowbooks
        shadowbooks.refresh()
    except Exception as e:
        print(f"    ! shadow books not refreshed ({str(e)[:100]})")
    for why in SKIPS:
        print(f"    ! row not saved: {why}")
    return {"status": "ok", "added": len(add), "external_added": n_ext}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="recompute every row, not just missing days")
    main(ap.parse_args().all)
