"""
BROKER IMPORT  —  apply a broker's activity file to a tracked real account, so the tracker never runs on assumed
share counts or prices.

    python -m pipeline.brokerimport robinhood_roth ~/Downloads/roth.csv
    python -m pipeline.brokerimport retire_a ~/Downloads/schwab.csv --format schwab

Reads the buys, sells and dividends dated after the book's `imported_through` and applies them to
state/external_books.json, one trading day at a time:

  - before each day's trades the book as it stood is kept as a phase, so earlier days are still priced on what the
    account held then (pipeline/navfill.py);
  - a SELL takes shares and their cost out of the position (pro rata across its lots) and puts the proceeds into the
    account's cash, carrying the sold lots' cost with them;
  - a BUY draws cash and that cash's share of carried cost, so swapping one stock for another does not reset the
    account's return (the "carried cost" method used since the Oct 20 rebalance);
  - a dividend is cash with no cost: a gain.

New money put into the account is not in an activity file's trades: add it with --deposit AMOUNT (counted at cost,
no gain). Formats: Robinhood's account activity report, and Schwab's transaction history export (Date, Action,
Symbol, Quantity, Price, Amount); the Schwab reader has not been checked against a real file yet, so read its
summary before trusting it. Nothing here needs the network.
"""
import copy
import csv
import datetime as dt
import sys

from .util import read_json, state_path, write_json

FILE = "external_books.json"


def _money(x):
    x = str(x or "").replace("$", "").replace(",", "").strip()
    neg = x.startswith("(") or x.startswith("-")
    x = x.strip("()-")
    return (-1 if neg else 1) * float(x) if x else 0.0


def _date(x):
    m, d, y = str(x).split(" ")[0].split("/")
    return dt.date(int(y), int(m), int(d)).isoformat()


def parse_robinhood(path):
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            code, tk = (r.get("Trans Code") or "").strip(), (r.get("Instrument") or "").strip()
            if not r.get("Activity Date") or not tk:
                continue
            if code in ("Buy", "Sell"):
                out.append({"date": _date(r["Activity Date"]), "ticker": tk, "action": code.upper(),
                            "shares": float(r["Quantity"]), "price": _money(r["Price"]), "amount": abs(_money(r["Amount"]))})
            elif code == "CDIV":
                out.append({"date": _date(r["Activity Date"]), "ticker": tk, "action": "DIV", "shares": 0.0, "price": 0.0,
                            "amount": abs(_money(r["Amount"]))})
    return out


def parse_schwab(path):
    out = []
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    head = next(i for i, r in enumerate(rows) if "Action" in r and "Symbol" in r)
    cols = {c.strip(): i for i, c in enumerate(rows[head])}
    for r in rows[head + 1:]:
        if len(r) <= cols["Symbol"] or not r[cols["Symbol"]].strip():
            continue
        act, tk = r[cols["Action"]].strip().lower(), r[cols["Symbol"]].strip()
        amount = abs(_money(r[cols["Amount"]]))
        if act in ("buy", "sell"):
            out.append({"date": _date(r[cols["Date"]]), "ticker": tk, "action": act.upper(),
                        "shares": abs(float(r[cols["Quantity"]].replace(",", ""))), "price": _money(r[cols["Price"]]),
                        "amount": amount})
        elif "dividend" in act or "div" in act.split():
            out.append({"date": _date(r[cols["Date"]]), "ticker": tk, "action": "DIV", "shares": 0.0, "price": 0.0,
                        "amount": amount})
    return out


PARSERS = {"robinhood": parse_robinhood, "schwab": parse_schwab}


def _spy_entry(book):
    for p in book.get("positions", []):
        for lot in p.get("lots", []):
            if lot.get("spy_price"):
                return lot["spy_price"]
    return (book.get("cash") or {}).get("spy_price")


def apply(book, txs, deposit=0.0):
    """Apply the transactions dated after book['imported_through'] to the book in place. Returns a summary dict."""
    done = str(book.get("imported_through") or "")
    txs = sorted([t for t in txs if t["date"] > done], key=lambda t: (t["date"], {"SELL": 0, "DIV": 1, "BUY": 2}[t["action"]]))
    spy = _spy_entry(book)
    cash = dict(book.get("cash") or {"amount": 0.0, "cost": 0.0, "spy_price": spy})
    pos = {p["ticker"]: p for p in book.get("positions", [])}
    summary = {"days": [], "sold": 0.0, "bought": 0.0, "dividends": 0.0, "skipped_before": done or None}
    if deposit:
        cash["amount"] = round(cash["amount"] + deposit, 2)
        cash["cost"] = round(cash["cost"] + deposit, 2)
    for day in sorted({t["date"] for t in txs}):
        before = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
        book.setdefault("phases", []).append({"until": before, "positions": copy.deepcopy(list(pos.values())),
                                              "cash": dict(cash)})
        for t in [x for x in txs if x["date"] == day]:
            tk = t["ticker"]
            if t["action"] == "SELL":
                p = pos.get(tk)
                if not p or p["shares"] < t["shares"] - 1e-6:
                    raise ValueError(f"{day}: sells {t['shares']:g} {tk} but the book holds {(p or {}).get('shares', 0):g}")
                frac = min(1.0, t["shares"] / p["shares"])
                c = p["cost_basis"] * frac
                for lot in p["lots"]:
                    lot["cost"] = round(lot["cost"] * (1 - frac), 2)
                    lot["shares"] = round(lot["shares"] * (1 - frac), 6)
                p["lots"] = [x for x in p["lots"] if x["shares"] > 1e-9]
                p["shares"] = round(p["shares"] - t["shares"], 6)
                p["cost_basis"] = round(p["cost_basis"] - c, 2)
                if p["shares"] <= 1e-9:
                    del pos[tk]
                cash["amount"] = round(cash["amount"] + t["amount"], 2)
                cash["cost"] = round(cash["cost"] + c, 2)
                summary["sold"] += t["amount"]
            elif t["action"] == "DIV":
                cash["amount"] = round(cash["amount"] + t["amount"], 2)
                summary["dividends"] += t["amount"]
            else:
                if t["amount"] > cash["amount"] + 0.01:
                    raise ValueError(f"{day}: buys ${t['amount']:,.2f} of {tk} with ${cash['amount']:,.2f} of cash in the "
                                     f"book: add the new money with --deposit")
                ratio = cash["cost"] / cash["amount"] if cash["amount"] else 1.0
                c = round(t["amount"] * ratio, 2)
                cash["amount"] = round(cash["amount"] - t["amount"], 2)
                cash["cost"] = round(cash["cost"] - c, 2)
                p = pos.setdefault(tk, {"ticker": tk, "shares": 0.0, "cost_basis": 0.0, "buy_date": day, "lots": []})
                p["lots"].append({"date": day, "shares": t["shares"], "cost": c, "price": t["price"], "spy_price": spy,
                                  "carried": True})
                p["shares"] = round(p["shares"] + t["shares"], 6)
                p["cost_basis"] = round(p["cost_basis"] + c, 2)
                summary["bought"] += t["amount"]
        summary["days"].append(day)
    if txs:
        cash["date"] = txs[-1]["date"]
        book["positions"], book["cash"] = list(pos.values()), cash
        book["active_from"] = book["imported_through"] = txs[-1]["date"]
    elif deposit:
        book["cash"] = cash
    summary.update(cash=cash["amount"], holdings={p["ticker"]: p["shares"] for p in pos.values()},
                   cost=round(cash["cost"] + sum(p["cost_basis"] for p in pos.values()), 2))
    return summary


def run(key, path, fmt="robinhood", deposit=0.0):
    d = read_json(state_path(FILE))
    if key not in d["books"]:
        raise SystemExit(f"no book '{key}': have {sorted(d['books'])}")
    s = apply(d["books"][key], PARSERS[fmt](path), deposit)
    write_json(state_path(FILE), d)
    return s


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    fmt = argv[argv.index("--format") + 1] if "--format" in argv else "robinhood"
    dep = float(argv[argv.index("--deposit") + 1]) if "--deposit" in argv else 0.0
    s = run(argv[0], argv[1], fmt, dep)
    print(f"{argv[0]}: {len(s['days'])} trading day(s) applied ({', '.join(s['days']) or 'nothing new'}); sold ${s['sold']:,.2f}, "
          f"bought ${s['bought']:,.2f}, dividends ${s['dividends']:,.2f}; cash now ${s['cash']:,.2f}; cost base ${s['cost']:,.2f}")
    print("holdings: " + ", ".join(f"{t} {n:g}" for t, n in sorted(s["holdings"].items())))
    print("Next: run Actions > NAV backfill with all = true to reprice the days since.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
