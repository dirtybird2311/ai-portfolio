"""
ALPACA PAPER ORDERS  —  run:  python -m pipeline.broker        (Actions > Paper orders; weekdays ~10:45 am ET)

In paper mode, places the approved trades from the latest rebuild and any daily-watch sale in your
Alpaca PAPER account, sells first, as market orders after the open. Fills are read back and recorded
at their actual paper prices when the plan is reconciled (tracking/rebuild), replacing the
"filled at the reference price" assumption.

Safety:
  - PAPER ONLY. The address is Alpaca's paper endpoint and is not configurable; with PAPER_MODE=0 this
    module does nothing (live trades are placed by you at Robinhood).
  - Keys come only from GitHub Secrets (ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY); without them the
    pipeline keeps the old paper behavior.
  - Every order carries the trade's stable id as its client_order_id, so a rerun can never place the
    same trade twice.
  - The pipeline trades only its own $10,000 book; Alpaca's extra paper cash is ignored.
"""
import math
import time
from datetime import datetime

import requests

from . import config
from .book import adhoc_plan_files, load_book, trade_key
from .notify import send, subject_line
from .util import now_et, read_json, state_path, write_json

PAPER_BASE = "https://paper-api.alpaca.markets/v2"      # paper only, on purpose
FINAL = {"filled", "canceled", "expired", "rejected", "done_for_day", "replaced", "stopped", "suspended"}
MAX_AGE_DAYS = 7          # a plan not placed within a week is recorded at reference prices instead
WAIT_SECONDS = 150        # how long to wait for the sells to fill before buying
PREOPEN_HOURS = 16        # with the market closed, orders are queued for the next open when it is this near (Alpaca
                          # holds day orders for the open), so a late or early job still trades at the planned open
_sleep = time.sleep


class BrokerUnavailable(RuntimeError):
    pass


def _keys():
    return (config.secret("ALPACA_API_KEY_ID", required=False), config.secret("ALPACA_API_SECRET_KEY", required=False))


def enabled():
    """Paper mode AND Alpaca keys set."""
    return bool(config.PAPER_MODE) and all(_keys())


def active_for(plan):
    return enabled() and bool(plan.get("paper"))


def paper_note():
    return ("paper mode: approved trades are placed automatically in Alpaca paper next trading morning"
            if enabled() else "paper mode: approved trades are recorded automatically")


def _req(http, method, path, **kw):
    kid, sec = _keys()
    h = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
    try:
        r = getattr(http, method)(PAPER_BASE + path, headers=h, timeout=30, **kw)
    except Exception as e:
        raise BrokerUnavailable(f"Alpaca unreachable: {str(e)[:120]}")
    return r


def _json(http, method, path, **kw):
    r = _req(http, method, path, **kw)
    if r.status_code not in (200, 201):
        raise BrokerUnavailable(f"Alpaca {method.upper()} {path}: HTTP {r.status_code} {r.text[:150]}")
    return r.json()


def symbol(ticker):
    return ticker.upper()           # Alpaca uses the dotted class form too (BRK.B)


def account(http=None):
    return _json(http or requests, "get", "/account")


def positions(http=None):
    return {p["symbol"]: float(p["qty"]) for p in _json(http or requests, "get", "/positions")}


def _age(plan):
    return (now_et().date() - datetime.fromisoformat(plan["date"][:10]).date()).days


def _fmt(x, places):
    return f"{x:.{places}f}".rstrip("0").rstrip(".")


# ==================================================================== placing
def submit(t, key, book, apos, http):
    """One order. Returns what to remember in the plan: {order_id, ...} or {failed: why}."""
    sym = symbol(t["ticker"])
    body = {"symbol": sym, "side": t["action"].lower(), "type": "market", "time_in_force": "day",
            "client_order_id": key}
    ref = float(t.get("ref_price") or 0)
    if t["action"] == "SELL":
        have = apos.get(sym, 0.0)
        if have <= 0:
            return {"failed": "no position at Alpaca to sell"}
        if t["amount"] == "all":
            mine = sum(p["shares"] for p in book["positions"] if p["ticker"] == t["ticker"] and p["account"] == t["account"])
            body["qty"] = _fmt(math.floor(min(mine or have, have) * 1e9) / 1e9, 9)
        else:
            body["notional"] = _fmt(min(float(t["amount"]), have * ref if ref else float(t["amount"])), 2)
    else:
        body["notional"] = _fmt(float(t["amount"]), 2)

    def post(b):
        return _req(http, "post", "/orders", json=b)

    r = post(body)
    if r.status_code in (200, 201):
        return {"order_id": r.json()["id"], "sent": body}
    text = r.text or ""
    low = text.lower()
    if "client_order_id" in low and ("unique" in low or "exist" in low or "duplicate" in low):
        d = _json(http, "get", "/orders:by_client_order_id", params={"client_order_id": key})   # placed by an earlier run
        return {"order_id": d["id"], "sent": body}
    if "fraction" in low:            # this stock can't be traded in fractions at Alpaca: use whole shares
        want = float(body["qty"]) if "qty" in body else (float(body["notional"]) / ref if ref else 0)
        whole = math.floor(want)
        if whole < 1:
            return {"failed": "not tradable in fractions at Alpaca and the amount is under one share"}
        b2 = {k: v for k, v in body.items() if k not in ("qty", "notional")}
        b2.update(qty=str(whole), client_order_id=key + "w")
        r = post(b2)
        if r.status_code in (200, 201):
            return {"order_id": r.json()["id"], "sent": b2, "note": "whole shares (not fractionable)"}
        text = r.text or ""
    return {"failed": f"HTTP {r.status_code}: {text[:150]}"}


def order(http, oid):
    return _json(http, "get", f"/orders/{oid}")


def wait_final(http, ids, seconds=WAIT_SECONDS):
    left = set(ids)
    end = time.time() + seconds
    while left:
        for oid in list(left):
            if order(http, oid)["status"] in FINAL:
                left.discard(oid)
        if not left or time.time() >= end:
            break
        _sleep(5)
    return not left


class AccountMismatch(Exception):
    """The Alpaca account behind the keys does not hold the portfolio's positions (wrong keys?)."""


def check_account(book, apos):
    """Refuse to trade when the book holds several stocks and Alpaca holds fewer than half of them: that is another
    account (on Nov 3 a key swapped for a day-trading bot sent this portfolio's orders to the bot's account)."""
    mine = sorted({p["ticker"] for p in book["positions"] if float(p.get("shares") or 0) > 0})
    here = [t for t in mine if apos.get(symbol(t), 0.0) > 0]
    if len(mine) >= 3 and len(here) < len(mine) / 2:
        raise AccountMismatch(f"the Alpaca account holds {len(here)} of the book's {len(mine)} stocks "
                              f"({', '.join(mine[:8])}{'...' if len(mine) > 8 else ''}): the API keys probably "
                              f"belong to another account. Nothing was placed.")


def session(clock):
    """(may place, the session's date, queued for the open) from Alpaca's clock."""
    if clock.get("is_open"):
        return True, now_et().date().isoformat(), False
    try:
        nxt = datetime.fromisoformat(str(clock.get("next_open")))
        hours = (nxt - now_et()).total_seconds() / 3600
    except (ValueError, TypeError):
        return False, None, False
    if 0 < hours <= PREOPEN_HOURS:
        return True, nxt.date().isoformat(), True
    return False, None, False


def place(http=None):
    """Place every approved, not-yet-placed trade from pending plans. With the market closed and the open near,
    the orders are queued at Alpaca for that open. Returns summary lines."""
    http = http or requests
    clock = _json(http, "get", "/clock")
    ok, day, queued = session(clock)
    if not ok:
        print(f"    Market closed (next open {clock.get('next_open')}); orders wait for the next run.")
        return []
    book = load_book()
    lines = []
    for pf in ["pending_plan.json"] + adhoc_plan_files():
        plan = read_json(state_path(pf))
        if not plan or plan.get("reconciled") or not plan.get("paper"):
            continue
        if plan.get("trade_date", plan["date"]) > day:
            continue                                       # not its trading day yet
        if _age(plan) > MAX_AGE_DAYS:
            continue
        orders = plan.setdefault("broker", {})
        todo = [t for t in plan["trades"] if t.get("status") == "approved" and t["id"] not in orders]
        if not todo:
            continue
        sells = [t for t in todo if t["action"] == "SELL"]
        buys = [t for t in todo if t["action"] == "BUY"]
        apos = positions(http)
        check_account(book, apos)
        retry = {}
        for group in (sells, buys):
            for t in group:
                key = trade_key(pf, plan, t)
                t["key"] = key
                res = dict(submit(t, key, book, apos, http), at=now_et().isoformat(timespec="minutes"))
                if queued and "failed" in res:             # before the open nothing is final: the next run tries again
                    retry[t["id"]] = res
                    continue
                if queued:
                    res["note"] = ((res.get("note") + "; ") if res.get("note") else "") + f"queued for the {day} open"
                orders[t["id"]] = res
                write_json(state_path(pf), plan)           # after every order: a crash can't lose an order id
            if group is sells and sells and not queued:
                ids = [orders[t["id"]]["order_id"] for t in sells if "order_id" in orders[t["id"]]]
                if ids and not wait_final(http, ids):
                    print("    ! some sells were still open after the wait; buying anyway (paper cash is ample)")
        for t in sells + buys:
            o = orders.get(t["id"]) or retry[t["id"]]
            amt = "ALL" if t["amount"] == "all" else f"${float(t['amount']):,.0f}"
            lines.append(f"{t['id']} {t['action']} {t['ticker']} {amt}: "
                         + (f"failed ({o['failed']})" if "failed" in o else "sent" + (f" ({o['note']})" if o.get("note") else "")))
    return lines


def status_lines(http=None):
    """Current state of today's orders, for the email."""
    http = http or requests
    out = []
    for pf in ["pending_plan.json"] + adhoc_plan_files():
        plan = read_json(state_path(pf))
        if not plan or plan.get("reconciled"):
            continue
        for t in plan["trades"]:
            o = (plan.get("broker") or {}).get(t["id"])
            if not o or "order_id" not in o:
                continue
            d = order(http, o["order_id"])
            q, p = float(d.get("filled_qty") or 0), d.get("filled_avg_price")
            out.append(f"{t['id']} {t['action']} {t['ticker']}: {d['status']}"
                       + (f", {q:g} shares at ${float(p):.2f}" if q and p else ""))
    return out


# ==================================================================== reading fills back
def fill_date(ts):
    """Alpaca's filled_at (UTC timestamp) as the New York trading date, or None."""
    if not ts:
        return None
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except ValueError:
        return None


def plan_fills(plan, plan_file, http=None):
    """{trade id: {state: filled|failed|unplaced|none, price, qty, why}}, or None when orders are still
    to be placed or not final yet (reconcile waits)."""
    http = http or requests
    orders = plan.get("broker") or {}
    age = _age(plan)
    out = {}
    try:
        for t in plan["trades"]:
            o = orders.get(t["id"])
            if not o:
                if t.get("status") != "approved":
                    out[t["id"]] = {"state": "none"}
                elif age <= MAX_AGE_DAYS:
                    return None
                else:
                    out[t["id"]] = {"state": "unplaced"}
                continue
            if "failed" in o:
                out[t["id"]] = {"state": "failed", "why": o["failed"]}
                continue
            d = order(http, o["order_id"])
            if d["status"] not in FINAL and age <= MAX_AGE_DAYS:
                return None
            q = float(d.get("filled_qty") or 0)
            if q > 0 and d.get("filled_avg_price"):
                out[t["id"]] = {"state": "filled", "qty": q, "price": float(d["filled_avg_price"]),
                                "date": fill_date(d.get("filled_at"))}
            else:
                out[t["id"]] = {"state": "failed", "why": d["status"]}
    except BrokerUnavailable as e:
        if age <= MAX_AGE_DAYS:
            print(f"    ! {e}; recording waits for the next run")
            return None
        print(f"    ! {e}; recording at reference prices instead")
        return {t["id"]: {"state": "unplaced" if t.get("status") == "approved" else "none"} for t in plan["trades"]}
    return out


def position_diff(book=None, http=None, tol=0.01):
    """Shares the pipeline's book says it owns vs what the Alpaca paper account holds."""
    book = book or load_book()
    mine = {}
    for p in book["positions"]:
        mine[symbol(p["ticker"])] = mine.get(symbol(p["ticker"]), 0.0) + p["shares"]
    theirs = positions(http)
    out = []
    for s in sorted(set(mine) | set(theirs)):
        a, b = mine.get(s, 0.0), theirs.get(s, 0.0)
        if abs(a - b) > max(tol, 0.01 * max(a, b)):
            out.append(f"{s}: book {a:g} shares, Alpaca {b:g}")
    return out


# ==================================================================== job
def main(session=None, folder=None, http=None):
    if not config.PAPER_MODE:
        print("Live mode: you place trades at Robinhood; nothing to do here.")
        return {"status": "skip"}
    if not enabled():
        print("Alpaca keys not set: paper trades are recorded at reference prices instead.")
        return {"status": "skip"}
    print("Placing paper orders in Alpaca...")
    try:
        lines = place(http)
    except AccountMismatch as e:
        text = (f"Paper orders were NOT placed: {e}\n\nCheck the ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY secrets in "
                f"this repository: they must be the portfolio paper account's keys.")
        print(text)
        send(subject_line("Paper orders", "FLAG", "wrong Alpaca account: nothing placed"), text, save_dir=folder)
        return {"status": "FLAG"}
    if not lines:
        print("    Nothing to place.")
        return {"status": "quiet"}
    _sleep(20)                                            # give market orders a moment to fill
    st = status_lines(http)
    text = "\n".join(["Orders sent to your Alpaca paper account:"] + [f"- {x}" for x in lines]
                     + ["", "Status now:"] + [f"- {x}" for x in st]
                     + ["", "Fills are recorded in the portfolio at the next tracking run (Friday) or rebuild."])
    print(text)
    failed = sum("failed" in x for x in lines)
    send(subject_line("Paper orders", "FLAG" if failed else "OK",
                      f"{len(lines) - failed} placed" + (f", {failed} failed" if failed else "")), text, save_dir=folder)
    return {"status": "FLAG" if failed else "OK"}


if __name__ == "__main__":
    from .runner import run_stage
    run_stage("orders", main)
