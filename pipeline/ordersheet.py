"""
ROBINHOOD ORDER SHEET  —  run:  python -m pipeline.ordersheet [--email]

Turns the latest rebuild's target weights into whole-share sells and buys for each real Robinhood account, using
current prices (Alpaca latest trade, Yahoo as the fallback), so nobody does the arithmetic by hand. Both accounts get
the same weights, so the larger one holds proportionally more shares. Sells are listed first (they fund the buys).
Writes reports/ordersheet/latest.md. It places no orders and changes no state.

Share counts come from state/external_books.json (assumed from earlier order lists: correct them there if they
differ from what Robinhood shows). Account value = current value of those holdings; cash already sitting in an
account is not counted, so add it if you want it invested.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import requests

from . import config
from .util import now_et, state_path, private_reports

LATEST = "https://data.alpaca.markets/v2/stocks/trades/latest"
OUT = "reports/ordersheet"


def latest_prices(tickers, get=requests.get, fallback=None):
    """{ticker: price}. Alpaca's latest IEX trade first; anything missing comes from `fallback(tickers)`."""
    out = {}
    kid = config.secret("ALPACA_API_KEY_ID", required=False)
    sec = config.secret("ALPACA_API_SECRET_KEY", required=False)
    if kid and sec:
        try:
            r = get(LATEST, headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec},
                    params={"symbols": ",".join(sorted(set(tickers))), "feed": "iex"}, timeout=30)
            if getattr(r, "status_code", 200) == 200:
                for sym, t in (r.json().get("trades") or {}).items():
                    out[sym] = float(t["p"])
        except Exception:
            pass
    missing = [t for t in tickers if t not in out]
    if missing and fallback:
        try:
            for t, v in (fallback(missing) or {}).items():
                out.setdefault(t, float(v))
        except Exception:
            pass
    return out


def yahoo_last(tickers):
    from .report import yahoo_closes
    c = yahoo_closes(tickers, None)
    return {t: float(c[t].dropna().iloc[-1]) for t in c.columns if c[t].notna().any()}


def whole_shares(weights, prices, value):
    """Target whole shares per ticker for an account worth `value`: floor each, then spend leftover cash one share
    at a time on the biggest shortfall, never overshooting a name by more than it undershoots. Returns (shares, cash)."""
    T = {t: weights[t] / 100 * value for t in weights}
    n = {t: int(T[t] // prices[t]) for t in weights}
    cash = value - sum(n[t] * prices[t] for t in n)
    while True:
        c = [t for t in weights if prices[t] <= cash and (T[t] - n[t] * prices[t]) > 0.5 * prices[t]]
        if not c:
            return n, cash
        t = max(c, key=lambda t: (T[t] - n[t] * prices[t]) / prices[t])
        n[t] += 1
        cash -= prices[t]


def plan(book, weights, prices):
    cur = {p["ticker"]: float(p["shares"]) for p in book["positions"]}
    value = (sum(sh * prices[t] for t, sh in cur.items() if t in prices) + float(book.get("invest_cash") or 0)
             + float((book.get("cash") or {}).get("amount") or 0))    # settled cash in the account is invested too
    tgt, cash = whole_shares(weights, prices, value)
    rows = []
    for t in sorted(set(cur) | set(tgt)):
        c, n = cur.get(t, 0), tgt.get(t, 0)
        if n != c:
            rows.append({"action": "SELL" if n < c else "BUY", "ticker": t, "shares": abs(n - c), "from": c, "to": n,
                         "price": prices.get(t), "dollars": abs(n - c) * prices.get(t, 0)})
    return {"value": value, "cash": cash, "rows": rows,
            "hold": {t: cur[t] for t in cur if tgt.get(t, 0) == cur[t]}}


def plan_fractional(book, weights, prices):
    """Fractional shares, buys only: the account's cash goes to the names furthest below target, each topped up
    toward its target dollars (scaled down evenly if the cash can't cover every shortfall). Nothing is sold."""
    cur = {p["ticker"]: float(p["shares"]) for p in book["positions"]}
    cash = float((book.get("cash") or {}).get("amount") or 0) + float(book.get("invest_cash") or 0)
    value = sum(sh * prices[t] for t, sh in cur.items() if t in prices) + cash
    short = {t: max(0.0, weights[t] / 100 * value - cur.get(t, 0) * prices[t]) for t in weights}
    need = sum(short.values())
    scale = min(1.0, cash / need) if need else 0.0
    rows = []
    for t in sorted(short, key=lambda t: -short[t]):
        d = round(short[t] * scale, 2)
        if d >= 1.0:                            # Robinhood's minimum fractional order
            n = d / prices[t]
            rows.append({"action": "BUY", "ticker": t, "shares": round(n, 4), "from": cur.get(t, 0),
                         "to": round(cur.get(t, 0) + n, 4), "price": prices[t], "dollars": d})
    spent = sum(r["dollars"] for r in rows)
    return {"value": value, "cash": cash - spent, "rows": rows, "fractional": True,
            "hold": {t: cur[t] for t in cur if t not in {r["ticker"] for r in rows}}}


def render(plans, labels, prices, stamp, target_date):
    L = [f"# Robinhood order sheet — {stamp}\n",
         f"Target weights from the rebuild of {target_date}. Prices are the latest trade; the market may move before you "
         "place orders, so a share count can shift by one. Sells first.\n"]
    for k, p in plans.items():
        sells = [r for r in p["rows"] if r["action"] == "SELL"]
        buys = [r for r in p["rows"] if r["action"] == "BUY"]
        L += [f"## {labels[k]} (about ${p['value']:,.0f})\n", "| Action | Shares | Ticker | Holding after | Price | Approx. $ |", "|---|---|---|---|---|---|"]
        if p.get("fractional"):
            L[-2:] = ["| Action | Dollar amount | Ticker | About shares | Shares after | Price |", "|---|---|---|---|---|---|"]
            for r in buys:
                L.append(f"| BUY | ${r['dollars']:,.2f} | {r['ticker']} | {r['shares']:g} | {r['to']:g} | {r['price']:.2f} |")
        else:
            for r in sells + buys:
                L.append(f"| {r['action']} | {r['shares']:g} | {r['ticker']} | {r['to']:g} | {r['price']:.2f} | {r['dollars']:,.0f} |")
        raised, spend = sum(r["dollars"] for r in sells), sum(r["dollars"] for r in buys)
        L.append(f"\nSells raise about ${raised:,.0f}; buys cost about ${spend:,.0f}; about ${p['cash']:,.0f} stays in cash. "
                 "No trade: " + (", ".join(f"{t} ({s:g})" for t, s in p["hold"].items()) or "none") + ".\n")
    return "\n".join(L)


def parse_cash(text):
    """'Account A=10000; Account B=5000' -> new all-cash accounts to invest from scratch."""
    out = {}
    for part in (text or "").replace("\n", ";").split(";"):
        if "=" in part:
            name, amt = part.rsplit("=", 1)
            out["new_" + "_".join(name.lower().split())] = {"label": name.strip() + " (new, all cash)", "positions": [],
                                                           "invest_cash": float(amt.replace("$", "").replace(",", ""))}
    return out


def build(get=requests.get, fallback=yahoo_last, plan_file=None, books_file=None, stamp=None, cash=None, fractional=None):
    pend = json.loads(Path(plan_file or state_path("pending_plan.json")).read_text())
    books = json.loads(Path(books_file or state_path("external_books.json")).read_text())["books"]
    if cash:                                   # only the new cash accounts: the existing books are not re-planned
        books = parse_cash(cash)
    weights = pend["target"]
    tickers = sorted(set(weights) | {p["ticker"] for b in books.values() for p in b["positions"]})
    prices = latest_prices(tickers, get, fallback)
    miss = [t for t in tickers if t not in prices]
    if miss:
        raise RuntimeError(f"no price for {', '.join(miss)}")
    if fractional:                             # dollar-amount buys for the named accounts only (e.g. robinhood_roth)
        books = {k: b for k, b in books.items() if k in fractional}
    plans = {k: (plan_fractional if fractional else plan)(b, weights, prices) for k, b in books.items()}
    labels = {k: b.get("label", k) for k, b in books.items()}
    return render(plans, labels, prices, stamp or now_et().strftime("%a %b %d, %I:%M %p ET"), pend["date"]), plans


def main(argv):
    cash = argv[argv.index("--cash") + 1] if "--cash" in argv else None
    frac = argv[argv.index("--fractional") + 1].split(",") if "--fractional" in argv else None
    md, _ = build(cash=cash, fractional=frac)
    root = private_reports("ordersheet")              # shows real holdings: private repo only
    name = "latest-cash.md" if cash else "latest-fractional.md" if frac else "latest.md"
    (root / name).write_text(md)
    (root / f"ordersheet-{now_et().date().isoformat()}{'-cash' if cash else '-fractional' if frac else ''}.md").write_text(md)
    print(f"Saved to the private repo: reports/ordersheet/ (not printed: this log is public)")
    if "--email" in argv:
        from . import notify
        notify.send(notify.subject_line("Robinhood order sheet", "OK", "sells first"), md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
