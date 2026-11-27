"""
THE BOOK: what you actually own, across both Robinhood accounts.

  state/holdings.json      cash + positions per account (Individual, IRA) with thesis/exit metadata
  state/trades.csv         every executed trade, with realized gains and holding days
  state/pending_plan.json  the last rebuild's trade list, waiting to be reconciled

Reconciliation: each rebuild posts a GitHub issue with one checkbox per trade. You tick what
you placed (optionally add your fill price, e.g. "@51.10"). The next run reads the issue and
updates the book, so skipped trades are known, not assumed.

Tax lots: every buy is its own lot; sales use the oldest lots first (FIFO, Robinhood's default),
and each lot sold is logged with its own gain and short/long-term status.
Idempotency: every trade carries a key; a trade already recorded is never recorded twice, even
if a run crashes halfway through reconciling and runs again.
Paper mode (config.PAPER_MODE): no checklist; approved trades are recorded as filled at their
reference price. `python -m pipeline.book --go-live` archives the paper book and starts fresh.
"""
import hashlib
import shutil
import sys
import os
import re
from datetime import date, timedelta

import pandas as pd
import requests

from .util import append_csv, now_et, read_json, state_path, write_json

ACCOUNTS = {"individual": "Individual", "ira": "IRA"}
STARTING_CASH = {"individual": 5000.0, "ira": 5000.0}
WASH_DAYS = 30


# ==================================================================== holdings
LONG_TERM_DAYS = 365


def load_book():
    b = read_json(state_path("holdings.json"))
    if not b or "accounts" not in b:
        b = {"updated": None, "accounts": {a: {"cash": c} for a, c in STARTING_CASH.items()}, "positions": []}
    for p in b["positions"]:           # older books had one blended lot per position
        if not p.get("lots"):
            p["lots"] = [{"date": p.get("buy_date"), "shares": p["shares"], "cost": p["cost_basis"]}]
    b.setdefault("applied", [])
    return b


def save_book(b):
    b["updated"] = now_et().date().isoformat()
    write_json(state_path("holdings.json"), b)


def positions_df(book, prices=None):
    df = pd.DataFrame(book.get("positions", []))
    if df.empty:
        return pd.DataFrame(columns=["ticker", "account", "shares", "cost_basis", "buy_date", "price", "value", "gain"])
    df["price"] = df.ticker.map(lambda t: (prices or {}).get(t)).fillna(df.cost_basis / df.shares)
    df["value"] = df.shares * df.price
    df["gain"] = df.value - df.cost_basis
    return df


def account_values(book, prices):
    pos = positions_df(book, prices)
    return {a: round(book["accounts"][a]["cash"] + float(pos[pos.account == a].value.sum()), 2) for a in ACCOUNTS}


def apply_trade(book, t, price, when, log=True):
    """t: {account, action BUY/SELL, ticker, amount or 'all'}. Updates cash/positions/lots; logs the trade
    (a sale is logged one row per tax lot sold). Returns a summary row, or None if nothing to sell."""
    acct, tick = t["account"], t["ticker"]
    pos = next((p for p in book["positions"] if p["ticker"] == tick and p["account"] == acct), None)
    row = {"date": when, "account": acct, "ticker": tick, "action": t["action"], "price": round(price, 4),
           "key": t.get("key", "")}
    if t["action"] == "BUY":
        amount = min(float(t["amount"]), book["accounts"][acct]["cash"])
        shares = amount / price
        book["accounts"][acct]["cash"] -= amount
        if pos:
            pos["shares"] += shares
            pos["cost_basis"] += amount
            pos.setdefault("lots", []).append({"date": when, "shares": shares, "cost": amount})
        else:
            pos = {"ticker": tick, "account": acct, "shares": shares, "cost_basis": amount, "buy_date": when,
                   "lots": [{"date": when, "shares": shares, "cost": amount}]}
            book["positions"].append(pos)
        for k in ("sector", "thesis", "exit_condition", "primary_driver", "conviction", "kind"):
            if t.get(k) is not None:
                pos[k] = t[k]
        row.update(shares=round(shares, 6), amount=round(amount, 2), realized_gain=0.0, holding_days="",
                   lot_date=when, term="")
        rows = [row]
    else:
        if not pos:
            return None
        shares = pos["shares"] if t.get("amount") == "all" else min(pos["shares"], float(t["amount"]) / price)
        left, rows = shares, []
        lots = sorted(pos.get("lots") or [], key=lambda x: str(x["date"]))
        for lot in lots:                                  # FIFO: oldest lot first
            if left <= 1e-9:
                break
            take = min(lot["shares"], left)
            basis = lot["cost"] * take / lot["shares"] if lot["shares"] else 0.0
            held = (pd.Timestamp(when) - pd.Timestamp(lot["date"])).days
            rows.append(dict(row, shares=round(take, 6), amount=round(take * price, 2),
                             realized_gain=round(take * price - basis, 2), holding_days=held, lot_date=lot["date"],
                             term="long" if held > LONG_TERM_DAYS else "short"))
            lot["cost"] -= basis
            lot["shares"] -= take
            left -= take
        pos["lots"] = [x for x in lots if x["shares"] > 1e-9]
        proceeds = shares * price
        pos["shares"] -= shares
        pos["cost_basis"] = sum(x["cost"] for x in pos["lots"])
        book["accounts"][acct]["cash"] += proceeds
        if pos["shares"] < 1e-6:
            book["positions"].remove(pos)
        elif pos["lots"]:
            pos["buy_date"] = pos["lots"][0]["date"]
        row = dict(row, shares=round(shares, 6), amount=round(proceeds, 2),
                   realized_gain=round(sum(r["realized_gain"] for r in rows), 2),
                   holding_days=rows[0]["holding_days"] if rows else "")
    if log:
        append_csv(state_path("trades.csv"), rows)
    return row


def trade_log():
    p = state_path("trades.csv")
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["date", "account", "ticker", "action", "amount", "realized_gain"])


# ==================================================================== wash sales
def wash_check(trades, book, prices, today=None):
    """Annotates each planned trade with 'wash': ok | warn | blocked (+ 'wash_note').
    The rule reaches across accounts: selling at a loss in Individual and buying the same stock in
    the IRA within 30 days forfeits the loss permanently. Confirm details with a tax professional."""
    today = pd.Timestamp(today or now_et().date())
    log = trade_log()
    if len(log):
        log["date"] = pd.to_datetime(log.date)
    recent = log[log.date >= today - timedelta(days=WASH_DAYS)] if len(log) else log
    pos = positions_df(book, prices)
    planned_buys = {(t["ticker"]) for t in trades if t["action"] == "BUY"}
    for t in trades:
        t["wash"], t["wash_note"] = "ok", ""
        if t["action"] == "SELL" and t["account"] == "individual":
            p = pos[(pos.ticker == t["ticker"]) & (pos.account == "individual")]
            if len(p) and p.iloc[0].gain < 0:
                bought = len(recent) and ((recent.ticker == t["ticker"]) & (recent.action == "BUY")).any()
                if t["ticker"] in planned_buys or bought:
                    t["wash"], t["wash_note"] = "blocked", "Loss sale with a purchase of the same stock within 30 days (any account)."
        if t["action"] == "BUY" and len(recent):
            loss_sales = recent[(recent.ticker == t["ticker"]) & (recent.action == "SELL") &
                                (recent.account == "individual") & (recent.realized_gain < 0)]
            if len(loss_sales):
                if t["account"] == "ira":
                    t["wash"], t["wash_note"] = "blocked", "Sold at a loss in Individual within 30 days; buying in the IRA would forfeit the loss."
                else:
                    t["wash"], t["wash_note"] = "warn", "Wash sale: the recent loss would be deferred into this purchase."
    return trades


# ==================================================================== GitHub checklist
def _gh():
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    return f"https://api.github.com/repos/{repo}", {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def checklist_body(plan):
    L = [f"Trades from the {plan['date']} rebuild. Tick each trade after placing it in Robinhood.",
         "Optional: add your fill price at the end of a line, e.g. `@51.10`. Unticked = not placed.", ""]
    for status, title in (("approved", "Ready to place"), ("flagged", "Flagged: your call (see email)")):
        rows = [t for t in plan["trades"] if t["status"] == status]
        if rows:
            L += [f"### {title}"] + [
                f"- [ ] {t['id']} · {t['action']} {t['ticker']} · {ACCOUNTS[t['account']]} · "
                f"{'ALL' if t['amount'] == 'all' else '$' + format(float(t['amount']), ',.0f')} · limit ${t['limit']:.2f} · fill "
                for t in rows] + [""]
    return "\n".join(L)


def post_checklist(plan, get=requests, local_dir=None, filename="checklist.md"):
    body = checklist_body(plan)
    gh = _gh()
    if gh:
        base, h = gh
        r = get.post(f"{base}/issues", headers=h, timeout=30,
                     json={"title": plan.get("title", f"Trades {plan['date']}"), "body": body, "labels": ["trades"]})
        if r.status_code in (200, 201):
            d = r.json()
            return {"number": d["number"], "url": d["html_url"]}
        print(f"  ! could not create GitHub issue: {r.status_code} {r.text[:120]}")
    path = state_path(filename)
    path.write_text(body)
    return {"number": None, "url": str(path)}


LINE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(T\d+)\b.*?(?:@\s*\$?(\d+(?:\.\d+)?))?\s*$")


def parse_checklist(body):
    done = {}
    for line in (body or "").splitlines():
        m = LINE.match(line)
        if m:
            done[m.group(2)] = (m.group(1).lower() == "x", float(m.group(3)) if m.group(3) else None)
    return done


def read_checklist(plan, get=requests):
    gh = _gh()
    num = (plan.get("checklist") or {}).get("number")
    if gh and num:
        base, h = gh
        r = get.get(f"{base}/issues/{num}", headers=h, timeout=30)
        if r.status_code == 200:
            return r.json().get("body", "")
    p = state_path(plan.get("checklist_file", "checklist.md"))
    return p.read_text() if p.exists() else ""


def close_checklist(plan, summary, get=requests):
    gh = _gh()
    num = (plan.get("checklist") or {}).get("number")
    if gh and num:
        base, h = gh
        get.post(f"{base}/issues/{num}/comments", headers=h, json={"body": summary}, timeout=30)
        get.patch(f"{base}/issues/{num}", headers=h, json={"state": "closed"}, timeout=30)


def trade_key(plan_file, plan, t):
    """Stable id for one planned trade: used to avoid recording it twice, and as the broker order id."""
    return t.get("key") or hashlib.sha256(f"{plan_file}|{plan['date']}|{t['id']}|{t['account']}|{t['action']}|"
                                          f"{t['ticker']}".encode()).hexdigest()[:16]


def adhoc_plan_files():
    """Daily-watch sell plans: one file per day (older versions used a single adhoc_plan.json)."""
    names = [p.name for p in state_path("x").parent.glob("adhoc_plan*.json")]
    return sorted(names)


def reconcile_all(prices, get=requests, min_age_days=0):
    """The rebuild plan (after min_age_days) and every daily-watch plan."""
    out = reconcile(prices, get, min_age_days=min_age_days)
    for f in adhoc_plan_files():
        out += reconcile(prices, get, plan_file=f)
    return out


def reconcile(prices, get=requests, plan_file="pending_plan.json", min_age_days=0, http=None):
    """Apply the trades you ticked on a checklist to the book. Returns a summary list.
    min_age_days: wait this long after the plan date before treating the checklist as final.
    Paper mode with Alpaca connected: trades are recorded at their actual paper fills, once every order
    is final. Paper mode without Alpaca: every approved trade counts as filled at its reference price."""
    plan = read_json(state_path(plan_file))
    if plan and (now_et().date() - pd.Timestamp(plan["date"]).date()).days < min_age_days:
        return []
    if not plan or plan.get("reconciled"):
        return []
    book = load_book()
    paper = bool(plan.get("paper"))
    overrides, notes, dates = {}, {}, {}
    if paper:
        from . import broker
        if broker.active_for(plan):
            fills = broker.plan_fills(plan, plan_file, http=http)
            if fills is None:                        # orders not placed or not final yet: try again next run
                return []
            ticks = {}
            for t in plan["trades"]:
                f = fills.get(t["id"], {"state": "none"})
                if f["state"] == "filled":
                    ticks[t["id"]] = (True, f["price"])
                    overrides[t["id"]] = f["qty"] * f["price"]      # what actually filled (partial fills too)
                    if f.get("date"):
                        dates[t["id"]] = f["date"]                  # the day it filled, not the plan's trade date
                    notes[t["id"]] = " [paper fill at Alpaca]"
                elif f["state"] == "unplaced" and t.get("status") == "approved":
                    ticks[t["id"]] = (True, None)    # never reached Alpaca: fall back to the reference price
                    notes[t["id"]] = " [paper, not placed at Alpaca: reference price]"
                else:
                    ticks[t["id"]] = (False, None)
                    if f.get("why"):
                        notes[t["id"]] = f" [Alpaca: {f['why']}]"
        else:
            # every approved trade counts as filled at its reference price; flagged ones don't
            ticks = {t["id"]: (t.get("status") == "approved", None) for t in plan["trades"]}
    else:
        ticks = parse_checklist(read_checklist(plan, get))
    logged = set(trade_log().get("key", pd.Series(dtype=str)).dropna().astype(str))
    applied = []
    # sells first so their cash funds the buys
    for t in sorted(plan["trades"], key=lambda x: x["action"] != "SELL"):
        key = trade_key(plan_file, plan, t)
        t["key"] = key
        done, fill = ticks.get(t["id"], (False, None))
        if not done:
            applied.append(f"{t['id']} {t['action']} {t['ticker']}: not placed" + notes.get(t["id"], ""))
            continue
        if key in book["applied"]:
            applied.append(f"{t['id']} {t['action']} {t['ticker']}: already recorded")
            continue
        price = fill or t.get("ref_price") or prices.get(t["ticker"])
        tt = dict(t, amount=overrides[t["id"]]) if t["id"] in overrides else t
        row = apply_trade(book, tt, price, dates.get(t["id"]) or plan.get("trade_date", plan["date"]), log=key not in logged)
        book["applied"].append(key)
        save_book(book)                    # after every trade, so a crash can't double-record
        applied.append(f"{t['id']} {t['action']} {t['ticker']} ({ACCOUNTS[t['account']]}): "
                       + (f"${row['amount']:,.2f} at ${price:.2f}" if row else "position not found, skipped")
                       + (notes.get(t["id"], " [paper]") if paper else ""))
    book["applied"] = book["applied"][-2000:]
    save_book(book)
    plan["reconciled"] = now_et().date().isoformat()
    write_json(state_path(plan_file), plan)
    if not paper:
        close_checklist(plan, "Recorded:\n" + "\n".join(f"- {a}" for a in applied), get)
    return applied


def go_live():
    """Archive the paper-trading book and start the real one from STARTING_CASH."""
    stamp = now_et().strftime("%Y-%m-%d")
    dest = state_path(f"paper_archive/{stamp}")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ["holdings.json", "trades.csv", "pending_plan.json", "rebuild_history.json",
                 "nav_history.csv", "performance.json", "drawdown.json"] + adhoc_plan_files():
        src = state_path(name)
        if src.exists():
            shutil.move(str(src), str(dest / name))
    print(f"Paper book archived to {dest}. Set PAPER_MODE=0 in GitHub (Settings > Variables) and "
          f"update STARTING_CASH in pipeline/book.py to your real balances.")


if __name__ == "__main__":
    if "--go-live" in sys.argv:
        go_live()
